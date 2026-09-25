"""REST + WebSocket API: the application service.

Owns conversations, messages, artifacts, approvals and the event log in
SQLite, and routes work to the selected engine. Engines run their own tool
loops; this service normalizes their events for the UI.
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress

from fastapi import APIRouter, HTTPException, WebSocket
from pydantic import BaseModel

from app.config import settings
from app.engines import (EngineAdapter, EngineEvent, ManagedOpenCodeServer,
                         OpenCodeServerEngine, ZenApiEngine)
from app.engines.detect import detect_all
from app.store import Store

log = logging.getLogger("instinct_muse")

# OpenCode round trips on slow models can run several minutes; give the full
# sync call room before giving up and recording a visible chat message.
REPLY_TIMEOUT_SECONDS = 600
SESSION_TIMEOUT_SECONDS = 60
# A dead-but-unnoticed client socket must never stall the reply pipeline.
SOCKET_WRITE_TIMEOUT_SECONDS = 5

KIND_BY_EXT = {
    ".md": "document", ".txt": "document", ".pdf": "document", ".doc": "document",
    ".html": "web", ".css": "web", ".js": "web", ".ts": "web", ".tsx": "web",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image", ".svg": "image",
    ".mp4": "video", ".mov": "video", ".webm": "video",
    ".mp3": "podcast", ".wav": "podcast", ".m4a": "podcast",
}


def artifact_kind(path: str) -> str:
    ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return KIND_BY_EXT.get(ext, "file")


class Hub:
    """Owns engines, storage and per-conversation stream state."""

    def __init__(self, store: Store):
        self.store = store
        self.engines: dict[str, EngineAdapter] = {}
        self.cli_probes: dict = {}
        self._managed: ManagedOpenCodeServer | None = None
        self._event_tasks: dict[str, asyncio.Task] = {}
        self._buffers: dict[str, list[str]] = {}  # session_id -> text deltas
        self._sockets: dict[str, set[WebSocket]] = {}  # conversation_id -> sockets
        self._sessions: dict[str, str] = {}  # engine_session_id -> conversation_id

    async def startup(self) -> None:
        self.cli_probes = await detect_all()
        server_url = settings.opencode_server_url
        if not server_url and self.cli_probes.get("opencode") and self.cli_probes["opencode"].available:
            self._managed = ManagedOpenCodeServer(
                self.cli_probes["opencode"].path or settings.opencode_binary, settings.opencode_server_port,
                settings.opencode_server_password)
            try:
                await self._managed.start()
                if await self._managed.wait_ready():
                    server_url = self._managed.base_url
                    log.info("spawned opencode serve at %s", server_url)
            except OSError as exc:
                log.warning("could not spawn opencode serve: %s", exc)
        if server_url:
            engine = OpenCodeServerEngine(server_url, settings.opencode_server_password,
                                             timeout=REPLY_TIMEOUT_SECONDS + 60)
            status = await engine.status()
            if status.available:
                self.engines[engine.id] = engine
                self._event_tasks[engine.id] = asyncio.create_task(self._pump(engine))
            else:
                log.warning("opencode server unavailable: %s", status.reason)
        zen = ZenApiEngine(settings.opencode_api_key, settings.opencode_base_url, settings.model)
        self.engines[zen.id] = zen
        self._event_tasks[zen.id] = asyncio.create_task(self._pump(zen))
        self._mark_interrupted_turns()

    def _mark_interrupted_turns(self) -> None:
        """Any conversation whose last message is from the user had its turn
        die with the previous process (app quit or crash). Say so in the chat
        instead of leaving the message looking silently unanswered."""
        for conv in self.store.list_conversations():
            msgs = self.store.list_messages(conv["id"])
            if msgs and msgs[-1]["role"] == "user":
                self.store.add_message(
                    conv["id"], "assistant",
                    "That turn was interrupted when the app quit - send the message again.")

    async def shutdown(self) -> None:
        for task in self._event_tasks.values():
            task.cancel()
        for engine in self.engines.values():
            with suppress(Exception):
                await engine.aclose()
        if self._managed:
            await self._managed.stop()

    # -- engine event pump ------------------------------------------------
    async def _pump(self, engine: EngineAdapter) -> None:
        try:
            async for ev in engine.events():
                await self._handle_event(engine, ev)
        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("event pump for %s died", engine.id)

    async def _handle_event(self, engine: EngineAdapter, ev: EngineEvent) -> None:
        cid = self._sessions.get(ev.session_id)
        if ev.type == "text_delta":
            self._buffers.setdefault(ev.session_id, []).append(ev.text)
            await self._broadcast(cid, {"type": "text_delta", "text": ev.text})
        elif ev.type == "message_done":
            text = "".join(self._buffers.pop(ev.session_id, []))
            if cid and text:
                self.store.add_message(cid, "assistant", text)
                self.store.log_event("message_done", {"session": ev.session_id}, cid)
            await self._broadcast(cid, {"type": "message_done"})
            if cid:
                await self._capture_artifacts(engine, ev.session_id, cid)
        elif ev.type == "permission_request":
            approval = self.store.add_approval(
                action=ev.action, detail=json.dumps(ev.detail)[:1000],
                conversation_id=cid, engine_permission_id=ev.permission_id)
            self.store.log_event("permission_request", approval, cid)
            await self._broadcast(cid, {"type": "approval", "approval": approval})
        elif ev.type == "error":
            if cid:
                self.store.log_event("error", {"text": ev.text}, cid)
            await self._broadcast(cid, {"type": "error", "text": ev.text})

    async def _capture_artifacts(self, engine: EngineAdapter, session_id: str, cid: str) -> None:
        """After a turn, record files the engine created into the Library."""
        if not isinstance(engine, OpenCodeServerEngine):
            return
        try:
            diffs = await engine.session_diff(session_id)
        except Exception:
            log.exception("diff fetch failed")
            return
        for diff in diffs:
            path = diff.get("file") or diff.get("path") or ""
            if not path or diff.get("status") not in (None, "added", "modified"):
                continue
            if self.store.find_artifact_by_path(path):
                continue
            try:
                content = await engine.file_content(path)
            except Exception:
                content = None
            art = self.store.add_artifact(
                kind=artifact_kind(path), path=path,
                title=path.rsplit("/", 1)[-1], content=content, conversation_id=cid)
            await self._broadcast(cid, {"type": "artifact", "artifact": art})

    async def _broadcast(self, cid: str | None, payload: dict) -> None:
        if not cid:
            return
        dead = []
        for ws in self._sockets.get(cid, set()):
            try:
                await asyncio.wait_for(ws.send_text(json.dumps(payload)),
                                       timeout=SOCKET_WRITE_TIMEOUT_SECONDS)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._sockets[cid].discard(ws)

    # -- chat ---------------------------------------------------------------
    async def send_user_message(self, cid: str, text: str) -> None:
        conv = self.store.get_conversation(cid)
        if not conv:
            raise KeyError(cid)
        engine = self.engines.get(conv["engine"])
        if not engine:
            raise RuntimeError(f"engine {conv['engine']} is not available")
        self.store.add_message(cid, "user", text)
        await self._maybe_autotitle(conv, text)
        session_id = conv["engine_session_id"]
        try:
            if not session_id:
                session_id = await asyncio.wait_for(
                    engine.create_session(title=conv["title"]),
                    timeout=SESSION_TIMEOUT_SECONDS)
                self.store.set_engine_session(cid, session_id)
            # Always (re)register the session->conversation mapping: after an
            # app or service restart the Hub is empty while conversations
            # still carry their engine_session_id, and replies without a
            # mapping were silently discarded.
            self._sessions[session_id] = cid
            provider_id = model_id = None
            if conv["model"] and "/" in conv["model"]:
                provider_id, model_id = conv["model"].split("/", 1)
            self._buffers.setdefault(session_id, [])
            await self._broadcast(cid, {"type": "status", "state": "working"})
            await asyncio.wait_for(engine.send(session_id, text, provider_id, model_id),
                                   timeout=REPLY_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            log.error("turn timeout conversation=%s session=%s", cid, session_id)
            with suppress(Exception):
                if session_id:
                    await engine.abort(session_id)
            await self._persist_error(cid, session_id or "-",
                "OpenCode took too long to respond. The turn was aborted; send the message again.")
        except Exception as exc:
            log.exception("turn failed conversation=%s session=%s", cid, session_id)
            await self._persist_error(cid, session_id or "-", f"OpenCode request failed: {exc}")

    async def _persist_error(self, cid: str, session_id: str, text: str) -> None:
        """Record a failed turn as a visible assistant message so the user is
        never left staring at a silent spinner, and so the failure survives a
        client reconnect."""
        with suppress(Exception):
            self.store.add_message(cid, "assistant", f"Error: {text}")
        self.store.log_event("error", {"text": text, "session": session_id}, cid)
        await self._broadcast(cid, {"type": "error", "text": text})
        await self._broadcast(cid, {"type": "message_done"})

    async def _maybe_autotitle(self, conv: dict, first_text: str) -> None:
        """Name a chat after its first user message instead of leaving every
        conversation titled "New chat"."""
        if (conv.get("title") or "").strip().lower() != "new chat":
            return
        flat = " ".join(first_text.split())
        snippet = flat[:48].rstrip()
        if len(flat) > 48:
            snippet = snippet.rsplit(" ", 1)[0] + "..."
        title = snippet or "Chat"
        self.store.touch_conversation(conv["id"], title)
        await self._broadcast(conv["id"],
                              {"type": "conversation_renamed",
                               "conversation_id": conv["id"], "title": title})


router = APIRouter(prefix="/api")
hub: Hub  # set by main at startup


class CreateConversation(BaseModel):
    title: str = "New chat"
    engine: str | None = None
    model: str | None = None


class ApprovalDecision(BaseModel):
    decision: str  # allow | always | deny


@router.get("/engines")
async def list_engines() -> dict:
    out = []
    for eid, engine in hub.engines.items():
        status = await engine.status()
        out.append(status.__dict__)
    for binary, probe in hub.cli_probes.items():
        if binary != "opencode" or not any(e["id"] == "opencode_server" and e["available"] for e in out):
            out.append({
                "id": f"cli:{binary}", "name": f"{binary} CLI",
                "available": probe.available, "reason": probe.reason,
                "detail": probe.path or "",
            })
    return {"engines": out, "default": settings.default_engine}


@router.get("/models")
async def list_models(engine: str) -> dict:
    adapter = hub.engines.get(engine)
    if not adapter:
        raise HTTPException(404, f"unknown engine {engine}")
    try:
        return {"models": [m.__dict__ for m in await adapter.models()]}
    except Exception as exc:
        raise HTTPException(502, f"could not list models: {exc}")


@router.post("/conversations", status_code=201)
async def create_conversation(body: CreateConversation) -> dict:
    engine = body.engine or settings.default_engine
    if engine not in hub.engines:
        raise HTTPException(400, f"engine {engine} is not available")
    return hub.store.create_conversation(body.title, engine, body.model)


@router.get("/conversations")
async def list_conversations() -> dict:
    return {"conversations": hub.store.list_conversations()}


@router.get("/conversations/{cid}")
async def get_conversation(cid: str) -> dict:
    conv = hub.store.get_conversation(cid)
    if not conv:
        raise HTTPException(404, "conversation not found")
    conv["messages"] = hub.store.list_messages(cid)
    return conv


@router.delete("/conversations/{cid}", status_code=204)
async def delete_conversation(cid: str) -> None:
    conv = hub.store.get_conversation(cid)
    if not conv:
        raise HTTPException(404, "conversation not found")
    session_id = conv["engine_session_id"]
    if session_id:
        engine = hub.engines.get(conv["engine"])
        if engine:
            with suppress(Exception):
                await engine.abort(session_id)
        hub._sessions.pop(session_id, None)
        hub._buffers.pop(session_id, None)
    hub.store.delete_conversation(cid)
    await hub._broadcast(cid, {"type": "conversation_deleted", "conversation_id": cid})
    for ws in list(hub._sockets.get(cid, set())):
        with suppress(Exception):
            await ws.close(code=1000)
    hub._sockets.pop(cid, None)


@router.get("/artifacts")
async def list_artifacts(kind: str | None = None) -> dict:
    return {"artifacts": hub.store.list_artifacts(kind)}


@router.get("/artifacts/{aid}")
async def get_artifact(aid: str) -> dict:
    art = hub.store.get_artifact(aid)
    if not art:
        raise HTTPException(404, "artifact not found")
    return art


@router.get("/approvals")
async def list_approvals(status: str | None = None) -> dict:
    return {"approvals": hub.store.list_approvals(status)}


@router.post("/approvals/{aid}")
async def decide_approval(aid: str, body: ApprovalDecision) -> dict:
    approval = hub.store.get_approval(aid)
    if not approval:
        raise HTTPException(404, "approval not found")
    if approval["status"] != "pending":
        raise HTTPException(409, f"approval already {approval['status']}")
    conv = hub.store.get_conversation(approval["conversation_id"]) if approval["conversation_id"] else None
    if conv and approval["engine_permission_id"]:
        engine = hub.engines.get(conv["engine"])
        if engine and conv["engine_session_id"]:
            response = {"allow": "once", "always": "always", "deny": "reject"}.get(body.decision)
            if not response:
                raise HTTPException(400, "decision must be allow, always or deny")
            await engine.reply_permission(
                conv["engine_session_id"], approval["engine_permission_id"],
                response, remember=body.decision == "always")
    status = "denied" if body.decision == "deny" else "approved"
    return hub.store.resolve_approval(aid, status)  # type: ignore[return-value]


async def conversation_ws(ws: WebSocket, cid: str) -> None:
    if not hub.store.get_conversation(cid):
        await ws.close(code=4404)
        return
    await ws.accept()
    hub._sockets.setdefault(cid, set()).add(ws)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_text(json.dumps({"type": "error", "text": "expected JSON"}))
                continue
            if msg.get("type") == "message" and msg.get("text", "").strip():
                # Run the engine round-trip in the background: the receive loop
                # must stay responsive, and a client disconnect or UI
                # chat-switch must not strand or crash an in-flight reply.
                asyncio.create_task(_send_safe(cid, msg["text"].strip()))
    except Exception:
        # WebSocketDisconnect on a normal close, WebSocketDisconnected/RuntimeError
        # on a mid-request disconnect race: all of them just mean "client gone".
        pass
    finally:
        hub._sockets.get(cid, set()).discard(ws)


async def _send_safe(cid: str, text: str) -> None:
    try:
        await hub.send_user_message(cid, text)
    except Exception:
        log.exception("send failed conversation=%s", cid)

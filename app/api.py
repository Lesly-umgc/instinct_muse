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

import time as _time
from pathlib import Path

import base64
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
        self._turn_starts: dict[str, float] = {}  # session_id -> turn start time
        self._sockets: dict[str, set[WebSocket]] = {}  # conversation_id -> sockets
        self._sessions: dict[str, str] = {}  # engine_session_id -> conversation_id
        self._shutting_down = False

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
        self._shutting_down = True
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
        """After a turn, record files the engine created into the Library.

        OpenCode's /session/{id}/diff only tracks changes inside a git
        worktree and comes back empty for ordinary agent writes, so the
        reliable signal is the workspace itself: any file touched since the
        turn started is something the agent made or changed this turn.
        """
        if not isinstance(engine, OpenCodeServerEngine):
            return
        for path in self._workspace_changes(session_id):
            if self.store.find_artifact_by_path(path):
                continue
            content: str | None = None
            try:
                p = Path(path)
                if p.stat().st_size <= 200_000:
                    content = p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                content = None
            art = self.store.add_artifact(
                kind=artifact_kind(path), path=path,
                title=path.rsplit("/", 1)[-1], content=content, conversation_id=cid)
            await self._broadcast(cid, {"type": "artifact", "artifact": art})
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

    def _workspace_changes(self, session_id: str) -> list[str]:
        """Files in the agent workspace created or modified since this turn."""
        start = self._turn_starts.get(session_id, 0.0)
        if not start:
            return []
        workspace = Path.home() / ".instinct_muse" / "workspace"
        if not workspace.is_dir():
            return []
        out: list[str] = []
        try:
            for p in workspace.rglob("*"):
                if not p.is_file() or p.name.startswith(".") or ".git" in p.parts:
                    continue
                try:
                    if p.stat().st_mtime >= start - 2:
                        out.append(str(p))
                except OSError:
                    continue
        except OSError:
            return []
        return out[:50]

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
            self._turn_starts[session_id] = _time.time()
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
            if self._shutting_down:
                # The process is exiting: leave the turn unanswered so the
                # next boot's sweep marks it as interrupted instead of
                # recording a spurious request failure.
                log.info("turn dropped during shutdown conversation=%s", cid)
                return
            log.exception("turn failed conversation=%s session=%s", cid, session_id)
            detail = str(exc) or type(exc).__name__
            await self._persist_error(cid, session_id or "-", f"OpenCode request failed: {detail}")

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


@router.get("/config")
def get_config():
    import os

    return {
        "initial_screen": os.environ.get("MUSE_INITIAL_SCREEN", ""),
        "initial_chat": os.environ.get("MUSE_INITIAL_CHAT", ""),
        "initial_settings_section": os.environ.get("MUSE_SETTINGS_SECTION", ""),
        "version": settings.app_version,
        "data_dir": str(Path.home() / ".instinct_muse"),
    }


@router.post("/attachments", status_code=201)
async def save_attachment(payload: dict) -> dict:
    """Save a user-picked file into the agent workspace uploads folder."""
    name = str(payload.get("name") or "attachment")
    safe = "".join(c for c in name if c.isalnum() or c in "._- ").strip() or "attachment"
    data = payload.get("data_b64") or ""
    try:
        raw = base64.b64decode(data)
    except Exception:
        raise HTTPException(400, "invalid base64 data")
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(413, "file too large (50 MB max)")
    uploads = Path.home() / ".instinct_muse" / "workspace" / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    dest = uploads / safe
    n = 1
    while dest.exists():
        dest = uploads / f"{dest.stem}-{n}{dest.suffix}"
        n += 1
    dest.write_bytes(raw)
    return {"path": str(dest)}


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




class GoalBody(BaseModel):
    title: str
    category: str = ""
    status_line: str = ""
    group_name: str = "Goals"


class GoalPatch(BaseModel):
    done: bool | None = None
    status_line: str | None = None
    title: str | None = None


@router.get("/goals")
async def list_goals() -> dict:
    return {"goals": hub.store.list_goals()}


@router.post("/goals", status_code=201)
async def create_goal(body: GoalBody) -> dict:
    return hub.store.create_goal(body.title, body.category, body.status_line, body.group_name)


@router.patch("/goals/{gid}")
async def update_goal(gid: str, body: GoalPatch) -> dict:
    goal = hub.store.update_goal(gid, done=body.done, status_line=body.status_line, title=body.title)
    if not goal:
        raise HTTPException(404, "goal not found")
    return goal


@router.delete("/goals/{gid}", status_code=204)
async def delete_goal(gid: str) -> None:
    hub.store.delete_goal(gid)


@router.get("/feed")
async def list_feed() -> dict:
    return {"editions": hub.store.list_feed()}


@router.post("/feed/items/{item_id}/love")
async def love_feed_item(item_id: str, body: dict) -> dict:
    hub.store.set_feed_item_loved(item_id, bool(body.get("loved", True)))
    return {"ok": True}


@router.post("/feed/refresh", status_code=202)
async def refresh_feed() -> dict:
    """Ask the engine for a fresh edition; stored as records, so the feed
    survives restarts and engine switches."""
    import asyncio as _asyncio
    _asyncio.create_task(_generate_feed())
    return {"ok": True}


async def _generate_feed() -> None:
    import json as _json
    import re as _re
    engine = hub.engines.get(settings.default_engine)
    if not engine:
        return
    sid = await engine.create_session("Feed edition")
    prompt = (
        "Write one short personal morning briefing edition for the app user. "
        "Return ONLY a JSON object: {\"label\": \"<weekday morning/afternoon/evening>\", "
        "\"items\": [{\"title\": \"<one-line headline>\", \"body\": \"<3-4 sentence briefing>\", "
        "\"links\": []}] } with exactly 2 items about technology and personal productivity. "
        "No markdown, no commentary, JSON only.")
    await engine.send(sid, prompt)
    text = ""
    async for ev in engine.events():
        if ev.session_id != sid:
            continue
        if ev.type == "text_delta":
            text += ev.text or ""
        elif ev.type == "message_done":
            break
        elif ev.type == "error":
            return
    m = _re.search(r"\{.*\}", text, _re.S)
    if not m:
        return
    try:
        data = _json.loads(m.group(0))
        hub.store.add_feed_edition(data.get("label", "Latest"), data.get("items", [])[:5])
    except (ValueError, TypeError):
        return


@router.get("/data/export")
async def export_data() -> dict:
    return hub.store.export_data()


@router.post("/data/reset", status_code=204)
async def reset_data() -> None:
    hub.store.reset_data()


@router.get("/ideas")
async def list_ideas() -> dict:
    return {"ideas": hub.store.list_ideas()}


@router.post("/ideas/{iid}/dismiss", status_code=204)
async def dismiss_idea(iid: str) -> None:
    hub.store.dismiss_idea(iid)


@router.post("/ideas/refresh", status_code=202)
async def refresh_ideas() -> dict:
    import asyncio as _asyncio
    _asyncio.create_task(_generate_ideas())
    return {"ok": True}


async def _generate_ideas() -> None:
    import json as _json
    import re as _re
    engine = hub.engines.get(settings.default_engine)
    if not engine:
        return
    sid = await engine.create_session("Ideas")
    prompt = (
        "Suggest 3 genuinely useful things you could do for the app user right now. "
        "Return ONLY a JSON array: [{\"title\": \"<one line>\", "
        "\"body\": \"<2-3 sentences on what you would do>\", \"category\": \"Productivity\"}]. "
        "No markdown, no commentary, JSON only.")
    await engine.send(sid, prompt)
    text = ""
    async for ev in engine.events():
        if ev.session_id != sid:
            continue
        if ev.type == "text_delta":
            text += ev.text or ""
        elif ev.type == "message_done":
            break
        elif ev.type == "error":
            return
    m = _re.search(r"\[.*\]", text, _re.S)
    if not m:
        return
    try:
        for idea in _json.loads(m.group(0))[:5]:
            hub.store.add_idea(idea.get("title", ""), idea.get("body", ""),
                               idea.get("category", ""))
    except (ValueError, TypeError):
        return


@router.get("/search")
async def global_search(q: str) -> dict:
    if not q.strip():
        return {"results": []}
    return {"results": hub.store.search(q.strip())}


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

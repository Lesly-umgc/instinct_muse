"""OpenCode engine: drive a local `opencode serve` instance over HTTP + SSE.

No API key is needed when the OpenCode CLI is already logged in - the server
rides the CLI's own provider auth. Auth methods and OAuth flows are exposed by
the server itself (GET /provider/auth, POST /provider/{id}/oauth/*) for engines
that still need a login.

API reference: https://opencode.ai/docs/server/
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

import httpx

from app.engines.base import EngineEvent, EngineStatus, ModelInfo


class OpenCodeServerEngine:
    id = "opencode_server"
    name = "OpenCode"

    def __init__(self, base_url: str, password: str = "", username: str = "opencode",
                 timeout: float = 300.0):
        auth = (username, password) if password else None
        self._base = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._base, auth=auth, timeout=timeout)
        # The SSE bus needs its own client: the shared one has a finite timeout
        # that would kill a long-lived event stream.
        self._sse_client = httpx.AsyncClient(base_url=self._base, auth=auth, timeout=None)
        self._sse_task: asyncio.Task | None = None
        self._responses: asyncio.Queue[EngineEvent] = asyncio.Queue()

    # -- status / catalog ------------------------------------------------
    async def status(self) -> EngineStatus:
        try:
            r = await self._client.get("/global/health")
            r.raise_for_status()
            version = r.json().get("version", "")
            return EngineStatus(self.id, self.name, True, detail=f"{self._base} (v{version})")
        except (httpx.HTTPError, ValueError) as exc:
            return EngineStatus(self.id, self.name, False,
                                reason=f"server not reachable at {self._base}: {exc}")

    async def models(self) -> list[ModelInfo]:
        r = await self._client.get("/provider")
        r.raise_for_status()
        data = r.json()
        defaults: dict[str, str] = data.get("default", {})
        connected = set(data.get("connected", []))
        out: list[ModelInfo] = []
        for provider in data.get("all", []):
            pid = provider.get("id", "")
            if connected and pid not in connected:
                continue  # only show providers the local login can actually use
            for mid, model in (provider.get("models") or {}).items():
                label = model.get("name") or mid
                out.append(ModelInfo(self.id, pid, mid, f"{provider.get('name', pid)} / {label}",
                                     is_default=defaults.get(pid) == mid))
        return out

    # -- sessions ---------------------------------------------------------
    async def create_session(self, title: str | None = None) -> str:
        body: dict[str, Any] = {}
        if title:
            body["title"] = title
        r = await self._client.post("/session", json=body)
        r.raise_for_status()
        return r.json()["id"]

    async def send(self, session_id: str, text: str,
                   provider_id: str | None = None, model_id: str | None = None) -> None:
        body: dict[str, Any] = {"parts": [{"type": "text", "text": text}]}
        if provider_id and model_id:
            body["model"] = {"providerID": provider_id, "modelID": model_id}
        # OpenCode 1.18.x can accept prompt_async with 204 while delivering no
        # SSE events. Use the sync endpoint and emit its durable response.
        r = await self._client.post(f"/session/{session_id}/message", json=body)
        r.raise_for_status()
        response = r.json()
        text = "".join(part.get("text", "") for part in response.get("parts", []) if part.get("type") == "text")
        await self._responses.put(EngineEvent("text_delta", session_id=session_id, text=text))
        await self._responses.put(EngineEvent("message_done", session_id=session_id))

    async def abort(self, session_id: str) -> None:
        r = await self._client.post(f"/session/{session_id}/abort")
        r.raise_for_status()

    async def reply_permission(self, session_id: str, permission_id: str,
                               response: str, remember: bool = False) -> None:
        r = await self._client.post(
            f"/session/{session_id}/permissions/{permission_id}",
            json={"response": response, "remember": remember})
        r.raise_for_status()

    # -- artifacts ---------------------------------------------------------
    async def session_diff(self, session_id: str) -> list[dict[str, Any]]:
        r = await self._client.get(f"/session/{session_id}/diff")
        r.raise_for_status()
        return r.json()

    async def file_content(self, path: str) -> str:
        r = await self._client.get("/file/content", params={"path": path})
        r.raise_for_status()
        data = r.json()
        return data.get("content", "") if isinstance(data, dict) else str(data)

    # -- events -------------------------------------------------------------
    async def events(self) -> AsyncIterator[EngineEvent]:
        # Sync /message gives a reliable response without relying on OpenCode's
        # currently unreliable SSE bus for text. The bus is still the only way
        # to see permission requests and session errors while a sync call is
        # blocked, so listen to it for those event types only.
        if self._sse_task is None:
            self._sse_task = asyncio.create_task(self._sse_loop())
        while True:
            yield await self._responses.get()

    async def _sse_loop(self) -> None:
        """Forward permission requests and session errors from the SSE bus."""
        while True:
            try:
                async with self._sse_client.stream("GET", "/event") as r:
                    r.raise_for_status()
                    async for line in r.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        try:
                            payload = json.loads(line[5:].strip())
                        except ValueError:
                            continue
                        ev = self._normalize(payload)
                        if ev and ev.type in ("permission_request", "error"):
                            await self._responses.put(ev)
            except asyncio.CancelledError:
                return
            except Exception:
                await asyncio.sleep(2)  # reconnect after the stream drops

    @staticmethod
    def _normalize(payload: dict[str, Any]) -> EngineEvent | None:
        etype = payload.get("type", "")
        props = payload.get("properties", {})
        if etype == "message.part.updated":
            part = props.get("part", {})
            if part.get("type") == "text":
                delta = props.get("delta") or ""
                return EngineEvent("text_delta", session_id=part.get("sessionID", ""), text=delta)
        elif etype == "permission.asked":
            return EngineEvent(
                "permission_request",
                session_id=props.get("sessionID", ""),
                permission_id=props.get("id", ""),
                action=props.get("permission", props.get("type", "action")),
                detail=props)
        elif etype == "session.idle":
            return EngineEvent("message_done", session_id=props.get("sessionID", ""))
        elif etype == "session.error":
            return EngineEvent("error", session_id=props.get("sessionID", ""),
                               text=json.dumps(props.get("error", props))[:500])
        return None

    async def aclose(self) -> None:
        if self._sse_task:
            self._sse_task.cancel()
            try:
                await self._sse_task
            except BaseException:
                pass
        await self._client.aclose()
        await self._sse_client.aclose()


class ManagedOpenCodeServer:
    """Spawn and own a local `opencode serve` child process."""

    def __init__(self, binary: str = "opencode", port: int = 4096, password: str = ""):
        self.binary, self.port, self.password = binary, port, password
        self.process: asyncio.subprocess.Process | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    async def start(self) -> None:
        import os
        from pathlib import Path
        env = dict(os.environ)
        if self.password:
            env["OPENCODE_SERVER_PASSWORD"] = self.password
        # Give the agent a real, writable working directory. Inheriting the
        # app's own CWD can land sessions at "/" or inside the read-only app
        # bundle, where every file creation fails.
        workspace = Path.home() / ".instinct_muse" / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        self.process = await asyncio.create_subprocess_exec(
            self.binary, "serve", "--port", str(self.port), "--hostname", "127.0.0.1",
            env=env, cwd=workspace,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)

    async def wait_ready(self, timeout: float = 20.0) -> bool:
        deadline = asyncio.get_event_loop().time() + timeout
        async with httpx.AsyncClient(base_url=self.base_url, timeout=2.0) as c:
            while asyncio.get_event_loop().time() < deadline:
                try:
                    r = await c.get("/global/health")
                    if r.status_code == 200:
                        return True
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.5)
        return False

    async def stop(self) -> None:
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 5.0)
            except asyncio.TimeoutError:
                self.process.kill()

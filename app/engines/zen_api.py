"""Direct OpenCode Zen API engine (fallback when the OpenCode CLI is absent).

Keeps the original API-key path working behind the engine interface: no local
CLI, no streaming, no permission requests - the model's tool calls are not
executed here (the engine runs its own loop; a plain chat-completion API has
none). Use the OpenCode engine for tool use and approvals.
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

from app.engines.base import EngineEvent, EngineStatus, ModelInfo
from app.providers.opencode_zen import OpenCodeZenProvider


class ZenApiEngine:
    id = "zen_api"
    name = "OpenCode Zen (API key)"

    def __init__(self, api_key: str, base_url: str, model: str):
        self._api_key, self._base_url, self._model = api_key, base_url, model
        self._queue: asyncio.Queue[EngineEvent] = asyncio.Queue()

    async def status(self) -> EngineStatus:
        if not self._api_key:
            return EngineStatus(self.id, self.name, False,
                                reason="OPENCODE_API_KEY not set (https://opencode.ai/zen)")
        return EngineStatus(self.id, self.name, True, detail=self._base_url)

    async def models(self) -> list[ModelInfo]:
        return [ModelInfo(self.id, "opencode", self._model, f"Zen / {self._model}", is_default=True)]

    async def create_session(self, title: str | None = None) -> str:
        import uuid
        return f"zen-{uuid.uuid4().hex[:12]}"

    async def send(self, session_id: str, text: str,
                   provider_id: str | None = None, model_id: str | None = None) -> None:
        provider = OpenCodeZenProvider(self._api_key, self._base_url, model_id or self._model)
        try:
            reply = await provider.chat([{"role": "user", "content": text}])
            await self._queue.put(EngineEvent("text_delta", session_id=session_id,
                                              text=reply.content or ""))
            await self._queue.put(EngineEvent("message_done", session_id=session_id))
        except Exception as exc:  # surfaced to the UI as a recoverable state
            await self._queue.put(EngineEvent("error", session_id=session_id, text=str(exc)))

    async def events(self) -> AsyncIterator[EngineEvent]:
        while True:
            yield await self._queue.get()

    async def reply_permission(self, session_id: str, permission_id: str,
                               response: str, remember: bool = False) -> None:
        raise NotImplementedError("zen_api engine has no permission requests")

    async def abort(self, session_id: str) -> None:
        return None

    async def aclose(self) -> None:
        return None

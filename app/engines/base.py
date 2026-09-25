"""Engine adapter interface.

Each engine (OpenCode server, Codex app server, direct API) runs its OWN tool
loop. The application service schedules work and normalizes what comes back:
streamed text, tool events, permission requests, errors and usage. It never
wraps a second competing agent loop around the engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol


@dataclass
class EngineStatus:
    id: str
    name: str
    available: bool
    reason: str = ""  # why unavailable, shown dimmed in the picker
    detail: str = ""  # e.g. detected binary path or server URL


@dataclass
class ModelInfo:
    engine: str
    provider_id: str
    model_id: str
    label: str
    is_default: bool = False


@dataclass
class EngineEvent:
    type: str  # text_delta | message_done | permission_request | error | status
    session_id: str = ""
    text: str = ""
    permission_id: str = ""
    action: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


class EngineAdapter(Protocol):
    id: str
    name: str

    async def status(self) -> EngineStatus: ...
    async def models(self) -> list[ModelInfo]: ...
    async def create_session(self, title: str | None = None) -> str: ...
    async def send(self, session_id: str, text: str,
                   provider_id: str | None = None, model_id: str | None = None) -> None:
        """Fire a user message; results arrive via events()."""
    def events(self) -> AsyncIterator[EngineEvent]:
        """One multiplexed event stream for the whole engine."""
    async def reply_permission(self, session_id: str, permission_id: str,
                               response: str, remember: bool = False) -> None: ...
    async def abort(self, session_id: str) -> None: ...
    async def aclose(self) -> None: ...

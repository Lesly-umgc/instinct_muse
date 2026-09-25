from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON string, as returned by the model


@dataclass
class ModelReply:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)


class ModelProvider(Protocol):
    async def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> ModelReply: ...

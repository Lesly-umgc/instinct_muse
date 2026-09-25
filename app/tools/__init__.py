"""Tool registry. Each tool runs inside the sandbox or through the broker, never in the gateway."""
import json
from typing import Any, Awaitable, Callable

from app.tools import sandbox_shell, browse

Tool = Callable[[dict[str, Any]], Awaitable[str]]

REGISTRY: dict[str, tuple[dict[str, Any], Tool]] = {
    "shell": (sandbox_shell.SCHEMA, sandbox_shell.run),
    "browse": (browse.SCHEMA, browse.run),
}


def schemas() -> list[dict[str, Any]]:
    return [schema for schema, _ in REGISTRY.values()]


async def dispatch(name: str, arguments: str) -> str:
    if name not in REGISTRY:
        return f"error: unknown tool {name}"
    try:
        args = json.loads(arguments or "{}")
    except json.JSONDecodeError:
        return "error: tool arguments were not valid JSON"
    _, fn = REGISTRY[name]
    return await fn(args)

"""Run a shell command in the sandbox container (see sandbox/)."""
import asyncio
from typing import Any

SCHEMA = {
    "type": "function",
    "function": {
        "name": "shell",
        "description": "Run a shell command inside the isolated sandbox workspace.",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
}

SANDBOX_CONTAINER = "muse-sandbox"


async def run(args: dict[str, Any]) -> str:
    proc = await asyncio.create_subprocess_exec(
        "docker", "exec", SANDBOX_CONTAINER, "sh", "-lc", args["command"],
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
    except asyncio.TimeoutError:
        proc.kill()
        return "error: command timed out after 60s"
    return out.decode(errors="replace")[-8000:]

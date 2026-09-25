"""Detect agent CLIs on the user's machine.

No scanner magic: probe PATH for each known binary, run a light version check,
and report available/unavailable with a human reason. The picker lights up
detected engines and dims the rest with the reason - the OpenMausBot pattern.
When a CLI is already logged in, the engine rides that login and no API key
is needed.
"""
from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass


@dataclass
class CliProbe:
    binary: str
    path: str | None
    version: str | None
    available: bool
    reason: str = ""


KNOWN_CLIS = {
    "opencode": "OpenCode",
    "codex": "Codex (ChatGPT)",
    "claude": "Claude Code",
}


async def probe(binary: str, timeout: float = 5.0) -> CliProbe:
    path = shutil.which(binary)
    if not path:
        return CliProbe(binary, None, None, False, f"'{binary}' not found on PATH")
    try:
        proc = await asyncio.create_subprocess_exec(
            path, "--version",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        version = out.decode(errors="replace").strip().splitlines()[0] if out else ""
        return CliProbe(binary, path, version or None, True)
    except (asyncio.TimeoutError, OSError) as exc:
        return CliProbe(binary, path, None, False, f"found at {path} but failed to run: {exc}")


async def detect_all(binaries: dict[str, str] | None = None) -> dict[str, CliProbe]:
    names = binaries or KNOWN_CLIS
    results = await asyncio.gather(*(probe(b) for b in names))
    return {p.binary: p for p in results}

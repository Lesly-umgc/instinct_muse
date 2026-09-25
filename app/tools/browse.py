"""Ask the browser worker for an accessibility-tree snapshot of a page."""
from typing import Any

import httpx

SCHEMA = {
    "type": "function",
    "function": {
        "name": "browse",
        "description": "Open a URL in the sandboxed browser and return an accessibility-tree snapshot.",
        "parameters": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
}

BROWSER_WORKER = "http://browser:8100"


async def run(args: dict[str, Any]) -> str:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(f"{BROWSER_WORKER}/snapshot", json={"url": args["url"]})
        resp.raise_for_status()
        return resp.json()["snapshot"][:12000]

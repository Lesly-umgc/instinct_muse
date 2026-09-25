"""OpenCode Zen provider.

Zen is OpenCode's model gateway (https://opencode.ai/docs/zen/). Models such as
big-pickle, glm-5.x, kimi-k2.x and deepseek-v4-* are served from an
OpenAI-compatible endpoint: {base_url}/chat/completions with a Bearer API key.
"""
from typing import Any

import httpx

from app.providers.base import ModelReply, ToolCall


class OpenCodeZenProvider:
    def __init__(self, api_key: str, base_url: str, model: str, timeout: float = 120.0):
        if not api_key:
            raise ValueError("OPENCODE_API_KEY is not set. Get one at https://opencode.ai/zen")
        self.model = model
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    async def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> ModelReply:
        body: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        resp = await self._client.post("/chat/completions", json=body)
        resp.raise_for_status()
        msg = resp.json()["choices"][0]["message"]
        calls = [
            ToolCall(id=c["id"], name=c["function"]["name"], arguments=c["function"].get("arguments") or "{}")
            for c in msg.get("tool_calls") or []
        ]
        return ModelReply(content=msg.get("content"), tool_calls=calls)

# instinct_muse

An open-source personal AI agent, inspired by the design Meta published for Muse.
The agent runs in a sandbox. Credentials and network access are controlled from outside it.

> Not affiliated with Meta. The architecture here follows Meta's public safety write-up:
> https://research.meta.ai/blog/security-and-safety-for-ai-agents-our-approach-with-muse

## How it fits together

| Muse (per Meta) | instinct_muse MVP |
| --- | --- |
| Per-user isolated Linux VM | One Docker Compose stack per user |
| Hatch harness in a systemd-nspawn container | `sandbox/` container: no network, dropped capabilities, non-root |
| hatch-authd surrogate tokens | `broker/token_broker.py` |
| Sentinel egress gate | `broker/egress_proxy.py` (allowlist + just-in-time token swap) |
| Chromium browser sub-agent on accessibility trees | `browser/worker.py` (Playwright) |
| Postgres app state | Postgres + pgvector |
| Muse Spark model | OpenCode Zen, swappable via `app/providers/` |
| iOS / Android / web clients | Web chat over WebSocket (`/ws/chat`) |

## Model: OpenCode Zen

The default provider is [OpenCode Zen](https://opencode.ai/docs/zen/), OpenCode's model gateway.
It uses the OpenAI-compatible `https://opencode.ai/zen/v1/chat/completions` endpoint with one API key.
The default model is `big-pickle`, which is listed as free. Set `MODEL` to any Zen
`/chat/completions` model id (for example `glm-5.3` or `kimi-k3`).

## Quick start

```bash
cp .env.example .env          # add OPENCODE_API_KEY
docker compose up --build
# chat: connect a WebSocket client to ws://localhost:8000/ws/chat
```

Local dev without Docker:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
pytest
uvicorn app.main:app --reload
```

## Roadmap (4-week MVP)

1. Gateway + chat: FastAPI, WebSocket, agent loop, OpenCode Zen provider
2. Sandbox: shell tool runs only inside the locked-down container
3. Browser worker: accessibility-tree snapshots, click/type actions
4. Trust layer: route all sandbox egress through the gate, surrogate tokens for connectors

After the MVP: Telegram/WhatsApp channel, scheduled jobs and sub-agents, prompt-injection classifier.

## License

Apache-2.0. See [LICENSE](LICENSE).

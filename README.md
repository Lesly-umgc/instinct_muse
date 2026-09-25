# instinct_muse

An open-source personal AI agent with a real UI, inspired by the design Meta published for
Muse and by OpenMausBot's bring-your-own-agent model. You pick the agent engine and model per
chat; the app detects agent CLIs already on your machine and rides their existing logins, so
there is no API key to configure when your OpenCode CLI is signed in.

> Not affiliated with Meta or xAI. Muse architecture reference:
> https://research.meta.ai/blog/security-and-safety-for-ai-agents-our-approach-with-muse

## How it fits together

```
Mac app (Tauri 2 + React)  -->  application service (FastAPI + SQLite)  -->  engine adapters
                                     |                                    --> OpenCode server (local CLI login)
                                     |                                    --> OpenCode Zen API (key, fallback)
                                     |                                    --> Codex app server (planned)
                                     +-- conversations, messages, Library,
                                         approvals, goals, scheduling, event log
```

- **The engine runs its own tool loop.** The app service owns conversations, memory, goals,
  approvals and scheduled work independently, so engines stay swappable.
- **Detection, not configuration.** On startup the service probes PATH for known agent CLIs
  (`opencode`, `codex`, `claude`). Detected engines light up in the picker; missing ones show
  dimmed with the reason. If `opencode` is found, the service spawns `opencode serve` itself.
- **Approvals in chat.** Engine permission requests (file writes, shell commands) become
  inline Allow / Always / Deny cards. The credential broker and egress allowlist gate sit
  behind them.
- **Library.** Files the agent creates during a chat are captured into the Library screen
  and persisted in SQLite.

| Muse (per Meta) | instinct_muse |
| --- | --- |
| Per-user isolated Linux VM | One Docker Compose stack per user (server deploy) |
| Hatch harness | `sandbox/` container: no network, dropped capabilities, non-root |
| hatch-authd surrogate tokens | `broker/token_broker.py` |
| Sentinel egress gate | `broker/egress_proxy.py` (allowlist + just-in-time token swap) |
| Muse Spark model | Any engine: local OpenCode login, OpenCode Zen API, Codex (planned) |
| iOS / Android / web clients | Mac app (Tauri + React), web UI over the same API |

## Quick start (Mac, native - recommended)

Requires Python 3.10+, Node 20+, and ideally the
[OpenCode CLI](https://opencode.ai) installed and logged in.

```bash
pip install -e ".[dev]"
cd ui && npm install && npm run build && cd ..
uvicorn app.main:app --reload
# open http://127.0.0.1:8000  (serves the built UI)
```

UI dev mode with hot reload:

```bash
uvicorn app.main:app --reload        # terminal 1
cd ui && npm run dev                 # terminal 2 -> http://127.0.0.1:5199
```

Desktop shell (once Rust is installed; the release bundles the service):

```bash
cd ui && npm ci && npx tauri dev
```

## Quick start (server deploy)

```bash
cp .env.example .env          # set OPENCODE_API_KEY for the zen_api engine
docker compose up --build
```

## First milestone

One faithful chat screen -> OpenCode connection -> streamed answer -> approved file
creation -> file appears in Library -> still there after restart.

Verified so far: the app service, SQLite persistence, detection probes, the OpenCode
adapter against the documented server API (mocked in tests), and the UI build.
**Not yet verified against a live logged-in OpenCode CLI** - that needs a machine with
OpenCode signed in (the event shapes in `app/engines/opencode_server.py` follow
https://opencode.ai/docs/server/ and should be smoke-tested there first).

## Tests

```bash
pytest          # storage, detection, adapter (mocked server), broker, agent loop
```

## Roadmap

- Phase 0: OpenCode spike - verify streaming, auth, cancel/resume and approval events
  against a live CLI; evaluate OpenPalm / PocketPaw for reuse ideas
- Phase 1 (this branch): app service + SQLite, engine adapters, detection, React UI shell
  (Chat / Feed / Ideas / Goals / Library), Tauri scaffold
- Phase 2: memory, goals, durable scheduling, feed generation, connectors through the broker
- Phase 3: Mac polish - quick chat shortcut, dictation, menu bar, signed + notarized installer
- Phase 4: remote worker for jobs that run while the Mac is asleep

## Credits

- Architecture inspiration: [OpenMausBot](https://github.com/milind-soni/OpenMausBot)
  (Apache-2.0) - independently written code, same driver-per-engine idea
- Research brief: see RESEARCH.md history / the project's planning notes

## License

Apache-2.0. See [LICENSE](LICENSE).

## Downloadable Mac build (Apple Silicon)

The v0.1.1-mac release contains an ad-hoc signed Apple Silicon `.dmg` built by GitHub Actions. The workflow smoke-tests the bundled service before publishing. Drag Instinct Muse
into Applications. On first launch, macOS may warn because it is not notarized:
right-click the app in Applications and select **Open**, then confirm. If macOS
still blocks it, use System Settings > Privacy & Security > Open Anyway. Do not
turn off Gatekeeper globally. Intel Macs are not supported by this build.

The DMG includes a frozen Python app service, started by the app on loopback
port 18764; no separate Python install is needed. If another process occupies that port, diagnostics will show the startup failure rather than connecting to the wrong server. The app still needs a working
[OpenCode CLI](https://opencode.ai) installed and logged in for local AI chat.
The OpenCode adapter has not yet been verified with a live login on a Mac.
Feed, Ideas, and Goals remain placeholders. This is a pre-release, not a
signed/notarized production app.

If startup or detection fails, open **Diagnostics** at the top of Chat. Service logs are at `~/.instinct_muse/service.log` and shell logs at `~/.instinct_muse/desktop.log`. Finder apps do not inherit Terminal PATH, so the app searches common local binary folders, including `~/.local/bin`. The installed binary was tested in CI, but the app still needs an interactive test with a logged-in OpenCode on a real Mac.

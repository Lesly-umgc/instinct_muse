"""Gateway: REST API, chat WebSocket, and the built UI if present."""
from contextlib import asynccontextmanager
from pathlib import Path
import sys

from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import api
from app.api import Hub, conversation_ws, router
from app.config import settings
from app.store import Store

UI_DIST = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "ui" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = Store(settings.resolved_db_path)
    api.hub = Hub(store)
    await api.hub.startup()
    yield
    await api.hub.shutdown()
    store.close()


app = FastAPI(title="Instinct Muse", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["tauri://localhost", "http://tauri.localhost", "https://tauri.localhost"], allow_methods=["*"], allow_headers=["content-type"])
# A loopback listener is not protected by CORS alone: reject browser requests
# from unrelated origins, including WebSocket upgrades that do not use CORS.
# This is a boundary against remote pages, not local malware/processes.
APP_ORIGINS = {"tauri://localhost", "http://tauri.localhost", "https://tauri.localhost",
               "http://127.0.0.1:18764", "http://localhost:18764",
               "http://127.0.0.1:5199", "http://localhost:5199"}


@app.middleware("http")
async def local_origin_guard(request: Request, call_next):
    origin = request.headers.get("origin")
    host = request.headers.get("host", "").lower()
    if origin and origin not in APP_ORIGINS:
        return PlainTextResponse("origin not allowed", status_code=403)
    if host and host.split(":", 1)[0] not in {"127.0.0.1", "localhost", "testserver"}:
        return PlainTextResponse("host not allowed", status_code=403)
    return await call_next(request)


app.include_router(router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "system": "instinct_muse"}


@app.websocket("/ws/conversations/{cid}")
async def chat(ws: WebSocket, cid: str) -> None:
    origin = ws.headers.get("origin")
    host = ws.headers.get("host", "").lower()
    if (origin and origin not in APP_ORIGINS) or (host and host.split(":", 1)[0] not in {"127.0.0.1", "localhost", "testserver"}):
        await ws.close(code=1008)
        return
    await conversation_ws(ws, cid)


if UI_DIST.is_dir():
    app.mount("/", StaticFiles(directory=UI_DIST, html=True), name="ui")

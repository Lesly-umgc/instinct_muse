"""Gateway: REST API, chat WebSocket, and the built UI if present."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles

from app import api
from app.api import Hub, conversation_ws, router
from app.config import settings
from app.store import Store

UI_DIST = Path(__file__).resolve().parent.parent / "ui" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = Store(settings.resolved_db_path)
    api.hub = Hub(store)
    await api.hub.startup()
    yield
    await api.hub.shutdown()
    store.close()


app = FastAPI(title="Instinct Muse", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/ws/conversations/{cid}")
async def chat(ws: WebSocket, cid: str) -> None:
    await conversation_ws(ws, cid)


if UI_DIST.is_dir():
    app.mount("/", StaticFiles(directory=UI_DIST, html=True), name="ui")

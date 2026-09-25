"""Gateway: web chat over WebSocket, plus a health check."""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from app.agent import run_turn

app = FastAPI(title="Instinct Muse")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/ws/chat")
async def chat(ws: WebSocket) -> None:
    await ws.accept()
    history: list[dict] = []
    try:
        while True:
            text = await ws.receive_text()
            history.append({"role": "user", "content": text})
            answer = await run_turn(history)
            history.append({"role": "assistant", "content": answer})
            await ws.send_text(answer)
    except WebSocketDisconnect:
        return

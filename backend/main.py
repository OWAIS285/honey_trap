import os

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
KILL_SWITCH = os.getenv("KILL_SWITCH", "false").lower() == "true"

app = FastAPI(title="honey-trap-api")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS or ["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def origin_allowed(origin: str | None) -> bool:
    return not ALLOWED_ORIGINS or origin in ALLOWED_ORIGINS


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "killSwitch": KILL_SWITCH}


@app.websocket("/ws/echo")
async def ws_echo(ws: WebSocket) -> None:
    if not origin_allowed(ws.headers.get("origin")):
        await ws.close(code=1008)
        return
    await ws.accept()
    try:
        while True:
            await ws.send_text(await ws.receive_text())
    except WebSocketDisconnect:
        pass

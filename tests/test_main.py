from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_healthz() -> None:
    body = client.get("/healthz").json()
    assert body["status"] == "ok"


def test_ws_echo() -> None:
    with client.websocket_connect("/ws/echo") as ws:
        ws.send_text("namaste")
        assert ws.receive_text() == "namaste"

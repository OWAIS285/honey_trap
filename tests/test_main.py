import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import main

client = TestClient(main.app)


def test_health() -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"


def test_ws_echo_from_allowed_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "ALLOWED_ORIGINS", ["https://app.example"])
    with client.websocket_connect("/ws/echo", headers={"origin": "https://app.example"}) as ws:
        ws.send_text("namaste")
        assert ws.receive_text() == "namaste"


def test_ws_rejects_unknown_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "ALLOWED_ORIGINS", ["https://app.example"])
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/echo", headers={"origin": "https://evil.example"}):
            pass

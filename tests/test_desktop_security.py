"""Desktop-mode HTTP/WS boundary: bearer token, loopback Host/Origin, health.

Desktop mode is activated only by a non-empty ``AMR_DESKTOP_TOKEN``. These tests
monkeypatch ``server.desktop.DESKTOP_TOKEN`` and build a fresh app so the desktop
middleware is installed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import engine
from server import desktop
from server.main import create_app

TOKEN = "desk-test-token"


def _auth(**extra: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {TOKEN}"}
    headers.update(extra)
    return headers


def _loopback_headers(**extra: str) -> dict[str, str]:
    headers = _auth(Host="127.0.0.1:8000")
    headers.update(extra)
    return headers


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(desktop, "DESKTOP_TOKEN", TOKEN)
    return TestClient(create_app())


def _make_image(tmp_path, name: str) -> str:
    f = tmp_path / name
    f.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-bytes")
    return str(f)


def test_desktop_mode_requires_token(client):
    assert client.get("/api/staging").status_code == 401
    assert client.get("/api/models").status_code == 401


def test_health_is_unauthenticated(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_health_reports_desktop(client):
    body = client.get("/health").json()
    assert body["desktop"] is True
    assert body["version"] == engine.VERSION


def test_auth_token_endpoint_is_404_in_desktop(client):
    assert client.post("/api/auth/token").status_code == 404


def test_wrong_token_rejected(client):
    resp = client.get("/api/staging", headers={"Authorization": "Bearer nope"})
    assert resp.status_code == 401


def test_correct_token_accepted(client):
    assert client.get("/api/staging", headers=_auth()).status_code == 200
    resp = client.put(
        "/api/staging",
        json=[],
        headers=_loopback_headers(Origin="http://127.0.0.1:8000"),
    )
    assert resp.status_code == 200


def test_mutating_request_rejects_foreign_origin(client):
    resp = client.put(
        "/api/staging",
        json=[],
        headers=_loopback_headers(Origin="http://evil.example"),
    )
    assert resp.status_code == 403


def test_mutating_request_rejects_foreign_host(client):
    resp = client.put(
        "/api/staging",
        json=[],
        headers=_auth(Host="evil.example:8000"),
    )
    assert resp.status_code == 403


def test_preflight_options_is_answered_by_cors(client):
    """An unauthenticated CORS preflight must reach CORSMiddleware, not get 401."""
    resp = client.options(
        "/api/staging",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") in {
        "*",
        "http://localhost:5173",
    }
    assert "PUT" in resp.headers.get("access-control-allow-methods", "")


def test_ws_rejects_missing_desktop_token(client):
    rejected = False
    try:
        with client.websocket_connect("/api/analyze/stream") as ws:
            ws.receive_json()
    except Exception:
        rejected = True
    assert rejected


def test_ws_accepts_desktop_token(client, monkeypatch, tmp_path):
    monkeypatch.setattr(
        engine, "process_image_to_base64", lambda p: "data:image/jpeg;base64,xxxx"
    )
    monkeypatch.setattr(engine, "_llamacpp_server_running", lambda: True)
    monkeypatch.setattr(
        engine,
        "analyze_asset_with_ai",
        lambda preview: {
            "ok": True,
            "data": {
                "new_filename": "cat_001",
                "tags": ["cat"],
                "suggested_category": "pets",
                "overall_visual_summary": "a cat",
                "topic": "animals",
                "description": "a cat photo",
            },
        },
    )

    src = _make_image(tmp_path, "cat.jpg")
    with client.websocket_connect(f"/api/analyze/stream?token={TOKEN}") as ws:
        ws.send_json({"files": [src], "profile": None, "settings": {}})
        events = []
        for _ in range(20):
            msg = ws.receive_json()
            events.append(msg)
            if msg.get("type") in ("complete", "cancelled"):
                break

    assert any(e["type"] == "asset_analyzed" for e in events)

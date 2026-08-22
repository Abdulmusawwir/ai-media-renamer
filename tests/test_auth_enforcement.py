"""Auth enforcement on mutating v2 API routes.

Auth is env-gated (``AMR_AUTH_ENABLED``). When off (the default local dev /
LAN-trust mode) every route is open; when on, mutating routes require a valid
``Authorization: Bearer <jwt>`` (REST) or a ``?token=<jwt>`` query param (WS).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import engine
from server import auth, deps
from server.main import app


@pytest.fixture
def auth_on(monkeypatch):
    monkeypatch.setattr(auth, "AUTH_ENABLED", True)
    monkeypatch.setenv("AMR_AUTH_ENABLED", "1")
    yield
    monkeypatch.setattr(auth, "AUTH_ENABLED", False)


def _token() -> str:
    return auth.create_access_token({"sub": "tester"})


def _make_image(tmp_path, name: str) -> str:
    f = tmp_path / name
    f.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-bytes")
    return str(f)


def test_mutating_routes_require_token_when_auth_on(auth_on):
    client = TestClient(app)
    assert client.post("/api/analyze", json={"files": ["x.jpg"]}).status_code == 401
    assert client.put("/api/staging", json=[]).status_code == 401
    assert (
        client.post("/api/staging/bulk", json={"selected": [], "updates": {}}).status_code
        == 401
    )
    assert (
        client.post(
            "/api/staging/import", json={"csv": "original_name,category\nx.jpg,pets"}
        ).status_code
        == 401
    )
    assert client.delete("/api/assets/foo.jpg").status_code == 401

    # Read-only GET endpoints stay open.
    assert client.get("/api/staging").status_code == 200


def test_mutating_routes_accept_valid_token(auth_on):
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {_token()}"}
    # Valid token -> no 401 (accepted / processed, not auth-rejected).
    assert client.put("/api/staging", json=[], headers=headers).status_code != 401
    # Garbage token -> 401.
    bad = {"Authorization": "Bearer not-a-real-token"}
    assert client.put("/api/staging", json=[], headers=bad).status_code == 401


def test_ws_stream_accepts_valid_token(auth_on, monkeypatch, tmp_path):
    monkeypatch.setattr(
        engine, "process_image_to_base64", lambda p: "data:image/jpeg;base64,xxxx"
    )
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
    client = TestClient(app)
    with client.websocket_connect(f"/api/analyze/stream?token={_token()}") as ws:
        ws.send_json({"files": [src], "profile": None, "settings": {}})
        events = []
        for _ in range(20):
            msg = ws.receive_json()
            events.append(msg)
            if msg.get("type") in ("complete", "cancelled"):
                break
    assert any(e["type"] == "asset_analyzed" for e in events)
    assert deps.get_active_staging()


def test_ws_stream_rejects_missing_token_when_auth_on(auth_on):
    client = TestClient(app)
    rejected = False
    try:
        with client.websocket_connect("/api/analyze/stream") as ws:
            ws.receive_json()  # server should have closed before sending anything
    except Exception:
        rejected = True
    assert rejected

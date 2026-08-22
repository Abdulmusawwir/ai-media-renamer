"""End-to-end tests for the v2 API: REST smoke + WebSocket analysis flow.

The WebSocket analysis pipeline is exercised against a *mocked* engine so the
test needs no llama.cpp server, FFmpeg, or ExifTool. To run against a real
llama.cpp server instead, point ``LLAMACPP_BASE_URL`` at it and remove the
monkeypatches below.
"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

import engine
from server import deps
from server.main import app


def _fake_asset(preview):
    """Stand-in for ``engine.analyze_asset_with_ai`` / ``analyze_document_with_ai``."""
    return {
        "ok": True,
        "data": {
            "new_filename": "cat_001",
            "tags": ["cat", "animal"],
            "suggested_category": "pets",
            "overall_visual_summary": "a cat",
            "topic": "animals",
            "description": "a cat photo",
        },
    }


def _make_image(tmp_path, name: str) -> str:
    f = tmp_path / name
    f.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-bytes")
    return str(f)


def _collect(ws, terminal=("complete", "cancelled"), limit=20):
    events = []
    for _ in range(limit):
        msg = ws.receive_json()
        events.append(msg)
        if msg.get("type") in terminal:
            break
    return events


def test_rest_smoke():
    client = TestClient(app)
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/api/environment").status_code == 200
    cfg = client.get("/api/config").json()
    assert isinstance(cfg, dict) and "logging" in cfg
    models = client.get("/api/models").json()
    assert "providers" in models and "current_provider" in models


def test_ws_analysis_flow(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "process_image_to_base64", lambda p: "data:image/jpeg;base64,xxxx")
    monkeypatch.setattr(engine, "analyze_asset_with_ai", _fake_asset)

    src = _make_image(tmp_path, "cat.jpg")
    client = TestClient(app)
    with client.websocket_connect("/api/analyze/stream") as ws:
        ws.send_json({"files": [src], "profile": None, "settings": {}})
        events = _collect(ws)

    types = [e["type"] for e in events]
    assert "extraction_progress" in types
    assert "asset_analyzed" in types
    assert "complete" in types

    analyzed = next(e for e in events if e["type"] == "asset_analyzed")
    # The asset's category is the engine's normalized form of the AI suggestion.
    assert analyzed["asset"]["category"] == engine.validate_category("pets")[0]
    assert deps.get_active_staging()  # run_analysis persisted staging


def test_ws_analysis_can_cancel(monkeypatch, tmp_path):
    def slow_extract(p):
        time.sleep(0.3)  # give the cancel message time to arrive
        return "data:image/jpeg;base64,xxxx"

    monkeypatch.setattr(engine, "process_image_to_base64", slow_extract)
    monkeypatch.setattr(engine, "analyze_asset_with_ai", _fake_asset)

    a = _make_image(tmp_path, "a.jpg")
    b = _make_image(tmp_path, "b.jpg")
    client = TestClient(app)
    with client.websocket_connect("/api/analyze/stream") as ws:
        ws.send_json({"files": [a, b], "profile": None, "settings": {}})
        ws.send_json({"action": "cancel"})
        events = _collect(ws)

    types = [e["type"] for e in events]
    assert "cancelled" in types

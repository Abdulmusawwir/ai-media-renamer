"""GET /api/models must not hang or 500 when the local llama.cpp server is down."""

from __future__ import annotations

from fastapi.testclient import TestClient

import engine
from server.main import app


def test_models_endpoint_survives_unreachable_server(monkeypatch):
    """When the active provider's available_models() raises (e.g. llama.cpp is
    unreachable), the route must still return 200 with an empty model list
    rather than propagate a 500 or hang."""

    class _BoomProvider:
        def available_models(self):
            raise RuntimeError("simulated unreachable llama.cpp server")

    monkeypatch.setattr(engine, "get_provider", lambda name: _BoomProvider())

    client = TestClient(app)
    resp = client.get("/api/models")
    assert resp.status_code == 200
    body = resp.json()
    assert body["models"] == []
    assert "providers" in body and "current_provider" in body


def test_models_endpoint_returns_catalog(monkeypatch):
    """A healthy provider's model list is surfaced in the response."""

    class _OkProvider:
        def available_models(self):
            return ["qwen2.5vl:7b"]

    monkeypatch.setattr(engine, "get_provider", lambda name: _OkProvider())

    client = TestClient(app)
    body = client.get("/api/models").json()
    assert body["models"] == ["qwen2.5vl:7b"]

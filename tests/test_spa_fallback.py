"""SPA fallback: client-side routes serve index.html, assets and API do not."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import server.main as main
from server import deps


@pytest.fixture
def dist(tmp_path):
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<html>spa-index</html>", encoding="utf-8")
    (root / "assets" / "app.js").write_text("console.log('app');", encoding="utf-8")
    return root


@pytest.fixture
def client(monkeypatch, dist):
    monkeypatch.setattr(main, "_DIST", dist)
    return TestClient(main.create_app())


def test_root_serves_index(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "spa-index" in resp.text


def test_client_route_serves_index(client):
    for route in ("/settings", "/analysis", "/analysis/nested/deep"):
        resp = client.get(route)
        assert resp.status_code == 200
        assert "spa-index" in resp.text


def test_missing_asset_returns_404(client):
    assert client.get("/assets/missing.js").status_code == 404


def test_api_route_wins_over_spa(client):
    resp = client.get("/api/config")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert "spa-index" not in resp.text


def test_unknown_api_path_returns_404(client):
    before = (
        deps.analysis_running(),
        deps.commit_running(),
        deps.get_active_staging(),
    )

    for route in ("/api/does-not-exist", "/api/nested/does-not-exist"):
        resp = client.get(route)
        assert resp.status_code == 404
        assert "spa-index" not in resp.text

    assert (
        deps.analysis_running(),
        deps.commit_running(),
        deps.get_active_staging(),
    ) == before


def test_existing_asset_is_not_shadowed(client):
    resp = client.get("/assets/app.js")
    assert resp.status_code == 200
    assert resp.text == "console.log('app');"

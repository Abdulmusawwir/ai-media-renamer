"""Release-metadata and security-guard regression tests."""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

import engine
from server.main import app


def test_updates_reports_current_version():
    """/api/updates/check must reflect the rewritten v2 version, not the stale
    v1.7.0 string that lingered in engine.VERSION during the rewrite."""
    client = TestClient(app)
    body = client.get("/api/updates/check").json()
    assert body["current_version"] == engine.VERSION
    assert engine.VERSION == "2.0.0"


def test_session_traversal_rejected():
    """A crafted session id containing '..' must be rejected, never escape
    SESSION_DIR. (Starlette collapses a bare '..' segment during path
    normalization, so that form is safe via 404; an id like '....json' still
    reaches the handler and must be rejected by the guard.)"""
    client = TestClient(app)
    assert client.get("/api/sessions/..").status_code != 200
    assert client.get("/api/sessions/....json").status_code == 400


def test_session_missing_returns_404_not_500():
    """A well-formed but absent session id should 404, not raise 500."""
    client = TestClient(app)
    resp = client.get("/api/sessions/does-not-exist.json")
    assert resp.status_code == 404


def test_browse_returns_expected_structure():
    """/api/browse lists the working directory with folder/file entries."""
    client = TestClient(app)
    body = client.get("/api/browse").json()
    assert "path" in body and "folders" in body and "files" in body
    assert "parent" in body

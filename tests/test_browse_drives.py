"""The folder picker must expose drive roots so users can change volumes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from server.main import app


def test_browse_includes_drives():
    response = TestClient(app).get("/api/browse")
    assert response.status_code == 200
    data = response.json()
    drives = data.get("drives")
    assert isinstance(drives, list)
    assert all(isinstance(drive, str) and drive.endswith(":\\") for drive in drives)

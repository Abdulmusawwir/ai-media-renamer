"""Desktop status endpoint, authoritative busy flags, and shutdown behavior."""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

import engine
import server.routes.models as models_routes
from server import deps, desktop
from server.main import create_app
from server.routes.analysis import run_analysis

TOKEN = "desk-test-token"


def _auth(**extra: str) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Host": "127.0.0.1:8000",
    }
    headers.update(extra)
    return headers


@pytest.fixture(autouse=True)
def _reset_runtime_state():
    deps.set_analysis_running(False)
    deps.set_commit_running(False)
    deps.set_active_staging([])
    with models_routes._STATE_LOCK:
        models_routes._DOWNLOAD_STATE.clear()
    yield
    deps.set_analysis_running(False)
    deps.set_commit_running(False)
    deps.set_active_staging([])
    with models_routes._STATE_LOCK:
        models_routes._DOWNLOAD_STATE.clear()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(desktop, "DESKTOP_TOKEN", TOKEN)
    return TestClient(create_app())


def test_status_shape_and_busy_flags(client, monkeypatch):
    monkeypatch.setattr(engine, "is_model_migration_running", lambda: True)
    deps.set_analysis_running(True)
    deps.set_commit_running(True)
    deps.set_active_staging([{"original_name": "a.jpg"}, {"original_name": "b.jpg"}])
    models_routes._record_state("model-x", state="downloading")

    resp = client.get("/api/desktop/status", headers=_auth())
    assert resp.status_code == 200
    assert resp.json() == {
        "analysis_running": True,
        "commit_running": True,
        "model_downloads_running": True,
        "model_migration_running": True,
        "setup_running": False,
        "staging_count": 2,
    }


def test_status_requires_token(client):
    assert client.get("/api/desktop/status").status_code == 401


def test_analysis_flag_cleared_on_exception(monkeypatch):
    def _boom(_name):
        raise RuntimeError("profile selection exploded")

    monkeypatch.setattr(engine, "set_active_profile", _boom)

    with pytest.raises(RuntimeError):
        run_analysis(["x.jpg"], "general", {})

    assert deps.analysis_running() is False


def test_commit_flag_cleared_on_exception(client, monkeypatch, tmp_path):
    class _DummyExif:
        def close(self) -> None:
            pass

    seen: dict[str, bool] = {}

    def _boom(*args, **kwargs):
        seen["running"] = deps.commit_running()
        raise RuntimeError("commit exploded")

    monkeypatch.setattr(engine, "ExifToolSession", lambda: _DummyExif())
    monkeypatch.setattr(engine, "execute_commit_batch", _boom)

    resp = client.post(
        "/api/commit",
        json={
            "assets": [
                {
                    "original_path": str(tmp_path / "x.jpg"),
                    "original_name": "x.jpg",
                    "staged_name": "x_new.jpg",
                }
            ],
            "target_dir": str(tmp_path),
        },
        headers=_auth(),
    )

    assert resp.status_code == 500
    assert seen["running"] is True
    assert deps.commit_running() is False


def test_model_downloads_running():
    assert models_routes.models_active_downloads() is False
    models_routes._record_state("m1", state="downloading")
    assert models_routes.models_active_downloads() is True
    models_routes._record_state("m1", state="done")
    assert models_routes.models_active_downloads() is False


def test_shutdown_stops_llama_and_exits(client, monkeypatch):
    stopped = threading.Event()
    exited = threading.Event()

    monkeypatch.setattr(engine, "stop_llamacpp_server", lambda: stopped.set())
    monkeypatch.setattr(desktop, "_exit_process", lambda: exited.set())

    resp = client.post("/api/desktop/shutdown", headers=_auth())
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    assert exited.wait(3.0)
    assert stopped.is_set()

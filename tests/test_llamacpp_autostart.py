"""Local llama.cpp server warm-up at backend startup.

The desktop installer ships ``llama-server.exe``; the backend starts it in the
background so the first analysis does not fail with "server is not running".
These tests cover the gating only — nothing is ever spawned here.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import engine
from server import main as server_main


def _cfg(gguf: str, base_url: str = "http://127.0.0.1:8080/v1") -> dict:
    return {"model": {"llamacpp": {"gguf_path": gguf, "base_url": base_url}}}


def test_autostart_requires_existing_gguf(monkeypatch, tmp_path):
    missing = tmp_path / "model.gguf"
    monkeypatch.setattr(engine, "config", _cfg(str(missing)))
    assert server_main.should_autostart_llamacpp() is False


def test_autostart_requires_local_base_url(monkeypatch, tmp_path):
    gguf = tmp_path / "model.gguf"
    gguf.write_bytes(b"GGUF")
    monkeypatch.setattr(engine, "config", _cfg(str(gguf), "http://192.168.1.50:8080/v1"))
    assert server_main.should_autostart_llamacpp() is False


def test_autostart_enabled_for_local_gguf(monkeypatch, tmp_path):
    gguf = tmp_path / "model.gguf"
    gguf.write_bytes(b"GGUF")
    monkeypatch.setattr(engine, "config", _cfg(str(gguf)))
    assert server_main.should_autostart_llamacpp() is True


def test_autostart_disabled_when_no_model_configured(monkeypatch):
    monkeypatch.setattr(engine, "config", {"model": {}})
    assert server_main.should_autostart_llamacpp() is False


def test_start_skips_spawn_when_already_running(monkeypatch, tmp_path):
    gguf = tmp_path / "model.gguf"
    gguf.write_bytes(b"GGUF")
    monkeypatch.setattr(engine, "config", _cfg(str(gguf)))
    monkeypatch.setattr(engine, "_llamacpp_server_running", lambda: True)

    def _boom(*_a, **_k):  # pragma: no cover - must never run
        raise AssertionError("ensure_llamacpp_server must not be called")

    monkeypatch.setattr(engine, "ensure_llamacpp_server", _boom)
    assert server_main.start_llamacpp_in_background() is False


def test_start_skips_when_gate_is_closed(monkeypatch):
    monkeypatch.setattr(engine, "config", {"model": {}})
    assert server_main.start_llamacpp_in_background() is False


def test_watchdog_ignores_foreign_servers(monkeypatch):
    monkeypatch.setattr(server_main, "_llamacpp_watchdog_managed", False)

    def _boom(*_a, **_k):  # pragma: no cover - must never run
        raise AssertionError("watchdog must not touch a foreign server")

    monkeypatch.setattr(engine, "ensure_llamacpp_server", _boom)
    server_main.llamacpp_watchdog_tick()


def test_watchdog_does_nothing_when_server_is_healthy(monkeypatch):
    monkeypatch.setattr(server_main, "_llamacpp_watchdog_managed", True)
    monkeypatch.setattr(server_main, "should_autostart_llamacpp", lambda: True)
    monkeypatch.setattr(engine, "_llamacpp_server_running", lambda: True)

    def _boom(*_a, **_k):  # pragma: no cover - must never run
        raise AssertionError("healthy server must not be restarted")

    monkeypatch.setattr(engine, "ensure_llamacpp_server", _boom)
    server_main.llamacpp_watchdog_tick()


def test_watchdog_restarts_a_dead_owned_server(monkeypatch):
    monkeypatch.setattr(server_main, "_llamacpp_watchdog_managed", True)
    monkeypatch.setattr(server_main, "should_autostart_llamacpp", lambda: True)
    monkeypatch.setattr(engine, "_llamacpp_server_running", lambda: False)
    calls = []
    monkeypatch.setattr(
        engine, "ensure_llamacpp_server",
        lambda timeout: calls.append(timeout) or True,
    )
    server_main.llamacpp_watchdog_tick()
    assert len(calls) == 1
    assert calls[0] == server_main._LLAMACPP_WARMUP_TIMEOUT


def test_watchdog_respects_the_autostart_gate(monkeypatch):
    monkeypatch.setattr(server_main, "_llamacpp_watchdog_managed", True)
    monkeypatch.setattr(server_main, "should_autostart_llamacpp", lambda: False)

    def _boom(*_a, **_k):  # pragma: no cover - must never run
        raise AssertionError("watchdog must respect the gate")

    monkeypatch.setattr(engine, "ensure_llamacpp_server", _boom)
    server_main.llamacpp_watchdog_tick()


def test_shutdown_leaves_a_foreign_server_running(monkeypatch):
    """A server another backend owns must survive this process's shutdown."""
    monkeypatch.setattr(server_main, "start_llamacpp_in_background", lambda: False)
    monkeypatch.setattr(engine, "_llamacpp_proc", None)
    calls = []
    monkeypatch.setattr(engine, "stop_llamacpp_server", lambda: calls.append(True))

    with TestClient(server_main.app):
        pass
    assert calls == []


def test_shutdown_stops_an_owned_server(monkeypatch):
    monkeypatch.setattr(server_main, "start_llamacpp_in_background", lambda: False)
    monkeypatch.setattr(engine, "_llamacpp_proc", object())
    calls = []
    monkeypatch.setattr(engine, "stop_llamacpp_server", lambda: calls.append(True))

    with TestClient(server_main.app):
        pass
    assert calls == [True]

"""Desktop backend entry point and setup-only bootstrap behavior."""

from __future__ import annotations

import sys

import pytest

import bootstrap
import desktop_backend
import engine


class _FakeWin:
    """Minimal SetupWindow stand-in for headless test runs."""

    root = object()

    def __init__(self) -> None:
        self.closed = False

    def set_step(self, *args) -> None:
        pass

    def set_progress(self, *args) -> None:
        pass

    def set_info(self, *args) -> None:
        pass

    def update(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


def test_argparse_rejects_unknown_flag():
    with pytest.raises(SystemExit) as exc:
        desktop_backend.main(["--definitely-not-a-flag"])
    assert exc.value.code == 2


def test_mark_onboarded_creates_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "USER_DATA_DIR", tmp_path)

    assert desktop_backend.main(["--mark-onboarded"]) == 0

    data = engine.load_setup_profile()
    assert data["onboarded"] is True
    assert data["profile"] == []


def test_mark_onboarded_preserves_existing_profile(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(
        engine,
        "load_setup_profile",
        lambda: {"onboarded": False, "profile": ["video", "image"]},
    )
    monkeypatch.setattr(
        engine,
        "save_setup_profile",
        lambda **kwargs: calls.append(kwargs) or {},
    )

    assert desktop_backend.main(["--mark-onboarded"]) == 0

    assert calls == [{"onboarded": True}]


def test_setup_calls_bootstrap_with_no_launch(monkeypatch):
    calls: list[list[str] | None] = []

    def _fake_main(argv=None):
        calls.append(argv)
        return 0

    monkeypatch.setattr(bootstrap, "main", _fake_main)

    assert desktop_backend.main(["--setup"]) == 0
    assert calls == [["--setup", "--no-launch", "--no-update-check"]]


def test_setup_failure_returns_nonzero(monkeypatch):
    monkeypatch.setattr(bootstrap, "main", lambda argv=None: 1)

    assert desktop_backend.main(["--setup"]) == 1


def test_smoke_test_returns_nonzero_when_health_never_ok(monkeypatch):
    class _FakeServer:
        def __init__(self) -> None:
            self.should_exit = False

        def run(self) -> None:
            pass

    class _FakeThread:
        def __init__(self, target, name=None, daemon=None) -> None:
            self._target = target

        def start(self) -> None:
            self._target()

        def join(self, timeout=None) -> None:
            pass

    server = _FakeServer()
    monkeypatch.setattr(desktop_backend, "_create_smoke_server", lambda host, port: server)
    monkeypatch.setattr(desktop_backend.threading, "Thread", _FakeThread)
    monkeypatch.setattr(desktop_backend, "_probe_health", lambda host, port: False)
    monkeypatch.setattr(desktop_backend, "SMOKE_TEST_TIMEOUT", 0.01)
    monkeypatch.setattr(desktop_backend, "SMOKE_TEST_POLL_INTERVAL", 0.001)
    monkeypatch.setattr(desktop_backend, "SMOKE_TEST_JOIN_TIMEOUT", 1.0)

    assert desktop_backend.main(["--smoke-test", "--port", "8123"]) == 1
    assert server.should_exit is True


def test_windowed_stdio_redirects_none(monkeypatch, tmp_path):
    monkeypatch.setenv("AMR_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    desktop_backend._configure_windowed_stdio()

    out = sys.stdout
    assert out is not None
    assert out is sys.stderr
    out.write("hello-backend\n")
    out.flush()
    out.close()

    log = tmp_path / "logs" / "backend-process.log"
    assert log.exists()
    assert "hello-backend" in log.read_text(encoding="utf-8")


def test_bootstrap_main_no_launch_returns_zero(monkeypatch):
    win = _FakeWin()
    calls: list[tuple[_FakeWin, bool]] = []

    monkeypatch.setattr(bootstrap, "SetupWindow", lambda: win)
    monkeypatch.setattr(
        bootstrap,
        "load_setup_profile",
        lambda: {"onboarded": True, "profile": []},
    )

    def _fake_finish(w, no_launch: bool) -> int:
        calls.append((w, no_launch))
        w.close()
        return 0

    monkeypatch.setattr(bootstrap, "_finish_setup", _fake_finish)

    assert bootstrap.main(["--no-launch"]) == 0
    assert calls == [(win, True)]
    assert win.closed is True


def test_launch_app_does_not_import_pywebview(monkeypatch):
    monkeypatch.delitem(sys.modules, "webview", raising=False)
    monkeypatch.delitem(sys.modules, "pywebview", raising=False)

    spawned: list[tuple[list[str], dict]] = []

    class _FakeProc:
        pid = 123

        def terminate(self) -> None:
            raise AssertionError("_launch_app must not terminate the child")

    def _fake_popen(args, **kwargs):
        spawned.append((args, kwargs))
        return _FakeProc()

    logs: list[str] = []
    monkeypatch.setattr(bootstrap.subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(bootstrap, "_log", logs.append)

    win = _FakeWin()
    bootstrap._launch_app(win)

    assert "webview" not in sys.modules
    assert "pywebview" not in sys.modules
    assert win.closed is True
    assert len(spawned) == 1

    args, kwargs = spawned[0]
    assert args == [sys.executable, str(bootstrap.BASE_DIR / "launch.py")]
    assert kwargs["cwd"] == str(bootstrap.BASE_DIR)
    assert kwargs["creationflags"] == bootstrap.subprocess.CREATE_NO_WINDOW
    assert logs

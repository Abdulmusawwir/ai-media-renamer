"""Windowed backend entry point for the Tauri desktop shell.

The shell launches this module as a child process. In a windowed build
``sys.stdout``/``sys.stderr`` are ``None``, so stdio is redirected to
``<data_root>/logs/backend-process.log`` *before* ``engine`` or ``server`` is
imported. All writable state lives under the resolved data root; nothing is
written into the install directory.
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from pathlib import Path

SMOKE_TEST_TIMEOUT = 30.0
SMOKE_TEST_POLL_INTERVAL = 0.5
SMOKE_TEST_JOIN_TIMEOUT = 10.0
BACKEND_LOG_NAME = "backend-process.log"


def _resolve_data_root() -> Path:
    """Resolve the data root without importing ``engine``."""
    override = os.environ.get("AMR_DATA_DIR")
    if override:
        return Path(override).expanduser()
    roaming = os.environ.get("APPDATA")
    if roaming:
        return Path(roaming) / "ai-media-renamer"
    return Path.home() / "AppData" / "Roaming" / "ai-media-renamer"


def _configure_windowed_stdio() -> None:
    """Point missing stdio streams at the backend process log.

    A windowed (``pythonw``/PyInstaller ``--windowed``) process has
    ``sys.stdout is None`` and ``sys.stderr is None``. Uvicorn and the engine
    write to both, so they must be redirected before those modules import.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return

    try:
        log_dir = _resolve_data_root() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stream = open(
            log_dir / BACKEND_LOG_NAME,
            "a",
            encoding="utf-8",
            buffering=1,
        )
    except OSError:
        stream = open(os.devnull, "a", encoding="utf-8", buffering=1)

    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


# Must run before importing engine/server: both may write to sys.stdout/stderr
# at import time.
_configure_windowed_stdio()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="desktop_backend",
        description="AI Media Renamer desktop backend",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--setup", action="store_true")
    parser.add_argument("--mark-onboarded", action="store_true")
    parser.add_argument("--no-launch", action="store_true")
    parser.add_argument("--no-update-check", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
    return parser


def _mark_onboarded() -> int:
    """Mark onboarding complete without clobbering an existing profile."""
    import engine

    data = engine.load_setup_profile()
    if data.get("onboarded"):
        return 0
    engine.save_setup_profile(onboarded=True)
    return 0


def _probe_health(host: str, port: int, timeout: float = 2.0) -> bool:
    """Return True when ``GET /health`` answers 200 on the given address."""
    from urllib.request import urlopen

    host_part = f"[{host}]" if ":" in host else host
    url = f"http://{host_part}:{port}/health"
    try:
        with urlopen(url, timeout=timeout) as response:
            status = getattr(response, "status", response.getcode())
            return status == 200
    except Exception:
        return False


def _create_smoke_server(host: str, port: int):
    """Build the in-process uvicorn server used by ``--smoke-test``."""
    import uvicorn

    config = uvicorn.Config(
        "server.main:app",
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )
    return uvicorn.Server(config)


def _run_smoke_test(host: str, port: int) -> int:
    """Boot uvicorn in-process, poll ``/health``, then shut it down."""
    try:
        server = _create_smoke_server(host, port)
    except Exception:
        return 1

    thread = threading.Thread(target=server.run, name="amr-smoke-uvicorn", daemon=True)
    thread.start()

    ready = False
    deadline = time.monotonic() + SMOKE_TEST_TIMEOUT
    try:
        while time.monotonic() < deadline:
            if _probe_health(host, port):
                ready = True
                break
            time.sleep(SMOKE_TEST_POLL_INTERVAL)
    finally:
        server.should_exit = True
        thread.join(timeout=SMOKE_TEST_JOIN_TIMEOUT)

    return 0 if ready else 1


def main(argv: list[str] | None = None) -> int:
    """Parse desktop flags and run the requested mode."""
    args = _build_parser().parse_args(argv)

    if args.setup:
        import bootstrap

        return bootstrap.main(["--setup", "--no-launch", "--no-update-check"])

    if args.mark_onboarded:
        return _mark_onboarded()

    if args.smoke_test:
        return _run_smoke_test(args.host, args.port)

    import uvicorn

    uvicorn.run(
        "server.main:app",
        host=args.host,
        port=args.port,
        log_level="warning",
        access_log=False,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

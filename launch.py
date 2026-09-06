"""Desktop launcher for AI Media Renamer v2.

Starts the FastAPI backend (which serves the built React frontend from
``frontend/dist``) on a free localhost port and opens it in the default browser.
This is the entry point bundled into the standalone ``.exe``.

The backend is bound on BOTH loopback addresses -- IPv4 ``127.0.0.1`` and IPv6
``::1`` -- because Windows enables ``IPV6_V6ONLY`` by default, so a single
``::`` socket does NOT accept IPv4-mapped connections. Browsers may reach the
app via either ``127.0.0.1`` or ``localhost`` (which often resolves to ``::1``),
and we must answer on both or ``fetch`` calls fail with "Failed to fetch" even
though the page itself loaded.
"""
from __future__ import annotations

import socket
import threading
import time
import webbrowser

import uvicorn

import server.main as _server

_HOSTS = ("127.0.0.1", "::1")


def _free_port(start: int = 8000, end: int = 8010) -> int:
    """Return a port that is free on every loopback address we bind to."""
    for port in range(start, end + 1):
        free = True
        for host in _HOSTS:
            family = socket.AF_INET6 if host == "::1" else socket.AF_INET
            try:
                with socket.socket(family, socket.SOCK_STREAM) as sock:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.bind((host, port))
            except OSError:
                free = False
                break
        if free:
            return port
    return start


def _open_browser(port: int) -> None:
    time.sleep(2)
    try:
        webbrowser.open_new(f"http://127.0.0.1:{port}")
    except Exception:
        pass


def _run_server(host: str, port: int) -> None:
    config = uvicorn.Config(
        _server.app, host=host, port=port, log_level="warning"
    )
    try:
        uvicorn.Server(config).run()
    except OSError as exc:
        # A missing address family (e.g. IPv6 disabled) shouldn't kill the app;
        # the other socket still serves the UI.
        print(f"[launch] could not bind {host}:{port}: {exc}")


def main() -> None:
    port = _free_port()
    threading.Thread(target=_open_browser, args=(port,), daemon=True).start()
    threads = [
        threading.Thread(target=_run_server, args=(host, port), daemon=True)
        for host in _HOSTS
    ]
    for t in threads:
        t.start()
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

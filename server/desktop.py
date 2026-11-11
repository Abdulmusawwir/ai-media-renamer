"""Desktop-mode boundary helpers.

Desktop mode is active only when ``AMR_DESKTOP_TOKEN`` is non-empty. The token
is supplied by the desktop shell to the child server process and is never
logged, persisted, or written to the CLI. In this mode every ``/api/*`` request
must carry ``Authorization: Bearer <token>`` and mutating requests must target a
loopback Host/Origin. ``/health`` stays unauthenticated so the shell can poll it
before it has a token.
"""

from __future__ import annotations

import os
import secrets
import sys
import threading
from urllib.parse import urlsplit

from fastapi import Request

import engine

# Read once at import time. The desktop shell sets the variable before spawning
# the server; an empty value means ordinary LAN/local mode.
DESKTOP_TOKEN: str = os.environ.get("AMR_DESKTOP_TOKEN", "").strip()

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})


def desktop_mode() -> bool:
    """Return True when the process was started by the desktop shell."""
    return bool(DESKTOP_TOKEN)


def bearer_token(request: Request) -> str | None:
    """Extract the bearer token from ``request`` (or None when absent)."""
    header = request.headers.get("Authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer":
        return None
    token = value.strip()
    return token or None


def ws_token_ok(token: str | None) -> bool:
    """Constant-time check of a WebSocket ``?token=`` value.

    Outside desktop mode this always returns True; the caller keeps the existing
    LAN ``auth.AUTH_ENABLED`` path instead.
    """
    if not desktop_mode():
        return True
    if not token:
        return False
    return secrets.compare_digest(token, DESKTOP_TOKEN)


def _split_host_port(host_header: str) -> tuple[str, str] | None:
    """Split ``host:port`` into lowercase host and port, or None if malformed."""
    host, sep, port = host_header.rpartition(":")
    if not sep or not host or not port.isdigit():
        return None
    return host.lower(), port


def host_allowed(request: Request) -> bool:
    """Return True when the request Host is ``127.0.0.1:<port>``/``localhost:<port>``."""
    raw = request.headers.get("host", "").strip()
    if not raw:
        return False
    parsed = _split_host_port(raw)
    if parsed is None:
        return False
    host, _port = parsed
    return host in _LOOPBACK_HOSTS


def origin_allowed(request: Request) -> bool:
    """Return True when a present Origin is a loopback ``http://`` origin.

    A missing Origin header is allowed (non-browser clients such as the shell's
    own health checks). A present origin must be exactly
    ``http://127.0.0.1:<port>`` or ``http://localhost:<port>``.
    """
    origin = request.headers.get("origin")
    if origin is None:
        return True
    origin = origin.strip()
    if not origin or origin.lower() == "null":
        return False
    parts = urlsplit(origin)
    if parts.scheme != "http":
        return False
    if parts.username or parts.password:
        return False
    try:
        port = parts.port
    except ValueError:
        return False
    if port is None:
        return False
    if parts.hostname is None or parts.hostname.lower() not in _LOOPBACK_HOSTS:
        return False
    return parts.path in ("", "/") and not parts.query and not parts.fragment


def is_desktop_request(path: str, method: str, request: Request) -> bool:
    """Return True when ``path`` must be guarded by the desktop boundary.

    ``/health`` and the LAN token issuer stay outside the boundary; in desktop
    mode the issuer is not registered so requests to it fall through to a 404.

    CORS preflight (``OPTIONS``) is also skipped so it reaches the inner
    ``CORSMiddleware`` instead of being rejected with a 401 before CORS can
    answer. Real requests keep requiring the bearer token.
    """
    del request  # kept for interface parity / future request-specific rules
    if not desktop_mode():
        return False
    if method == "OPTIONS":
        return False
    if path == "/health":
        return False
    if path == "/api/auth/token":
        return False
    return path.startswith("/api/")


def _flush_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:
            pass


def _exit_process() -> None:
    """Hard-exit the process. Isolated so tests can monkeypatch it."""
    os._exit(0)


def begin_shutdown(delay: float = 0.05) -> threading.Timer:
    """Stop llama-server, flush output, then exit from a short background timer.

    The small delay lets the HTTP response for ``POST /api/desktop/shutdown``
    reach the client before the process disappears.
    """

    def _run() -> None:
        try:
            engine.stop_llamacpp_server()
        except Exception:
            pass
        _flush_streams()
        _exit_process()

    timer = threading.Timer(delay, _run)
    timer.daemon = True
    timer.start()
    return timer

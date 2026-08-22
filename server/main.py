"""FastAPI application entrypoint for the AI Media Renamer v2 backend.

Wraps ``engine.py`` behind a REST + WebSocket API. Lifecycle: load config on
startup, register routes, run with uvicorn (auto-port 8000..8010 if the default
is taken). The built React frontend (``frontend/dist``) is served at "/" when
present; otherwise the API is reachable on its own.
"""

from __future__ import annotations

import os
import socket
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import engine
from server import auth as amr_auth
from server import security as amr_security
from server.routes import register_routes

# Built frontend output (from ``frontend/`` via ``npm run build``). When present
# it is served at "/" (API routes registered above win over the static mount).
_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

# NOTE: Allowing all origins is acceptable for a local single-user tool driven
# from localhost. If you expose this server on a LAN (e.g. --host 0.0.0.0),
# restrict ``allow_origins`` to trusted frontend origins and enable auth
# (see server/auth.py, env AMR_AUTH_ENABLED=1). The config key
# ``server.cors_origins`` (a list) overrides this default when present.
CORS_ALLOW_ORIGINS = ["*"]


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(title="AI Media Renamer API", version="2.0.0")

    # CORS origins: prefer an explicit ``server.cors_origins`` list from config
    # when present, otherwise fall back to the open default.
    cfg_origins = engine.config.get("server", {}).get("cors_origins")
    allow_origins = cfg_origins if isinstance(cfg_origins, list) and cfg_origins else CORS_ALLOW_ORIGINS

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Optional per-IP rate limiting. Enabled only when AMR_RATE_LIMIT is a
    # positive integer; otherwise this middleware is not installed.
    rate_limit = os.environ.get("AMR_RATE_LIMIT", "").strip()
    if rate_limit.isdigit() and int(rate_limit) > 0:
        app.add_middleware(
            amr_security.RateLimitMiddleware, max_requests=int(rate_limit)
        )

    register_routes(app)

    # LAN-mode auth token issuer. When auth is disabled this reports the state
    # without issuing a token so clients can detect the mode.
    @app.post("/api/auth/token", tags=["auth"])
    def auth_token() -> dict:
        if not amr_auth.AUTH_ENABLED:
            return {"enabled": False}
        return {"enabled": True, "token": amr_auth.create_access_token({})}

    @app.on_event("startup")
    def _startup() -> None:
        # Ensure the engine config is loaded and environment probes are usable.
        engine.load_config(quiet=True)
        # Best-effort: confirm the environment check runs without raising.
        try:
            engine.check_environment()
        except Exception:
            pass

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok", "version": "2.0.0"}

    # Serve the built React frontend LAST so API routes and /health (registered
    # above) match first and are not swallowed by the catch-all mount.
    if _DIST.is_dir():
        app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")

    return app


app = create_app()


def _port_is_free(host: str, port: int) -> bool:
    """Return True if ``port`` on ``host`` can be bound right now."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
        return True


def pick_port(host: str = "127.0.0.1", start: int = 8000, end: int = 8010) -> int:
    """Probe ports start..end and return the first free one (default 8000)."""
    for port in range(start, end + 1):
        if _port_is_free(host, port):
            return port
    raise RuntimeError(f"no free port in range {start}..{end}")


def run(host: str = "127.0.0.1", port: int | None = None) -> None:
    """Launch the uvicorn server, auto-selecting a port if none is given."""
    import uvicorn

    if port is None:
        port = pick_port(host)

    uvicorn.run("server.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    run()

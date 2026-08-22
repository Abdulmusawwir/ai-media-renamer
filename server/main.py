"""FastAPI application entrypoint for the AI Media Renamer v2 backend.

Wraps ``engine.py`` behind a REST + WebSocket API. Lifecycle: load config on
startup, register routes, run with uvicorn (auto-port 8000..8010 if the default
is taken). The frontend is served separately (Phase 2) and is not mounted here
yet.
"""

from __future__ import annotations

import socket

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import engine
from server.routes import register_routes

# NOTE: Allowing all origins is acceptable for a local single-user tool driven
# from localhost. If you expose this server on a LAN (e.g. --host 0.0.0.0),
# restrict ``allow_origins`` to trusted frontend origins and enable auth
# (see server/auth.py, env AMR_AUTH_ENABLED=1).
CORS_ALLOW_ORIGINS = ["*"]


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(title="AI Media Renamer API", version="2.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ALLOW_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_routes(app)

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

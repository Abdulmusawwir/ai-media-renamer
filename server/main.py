"""FastAPI application entrypoint for the AI Media Renamer v2 backend.

Wraps ``engine.py`` behind a REST + WebSocket API. Lifecycle: load config on
startup, register routes, run with uvicorn (auto-port 8000..8010 if the default
is taken). The built React frontend (``frontend/dist``) is served at "/" when
present; otherwise the API is reachable on its own.
"""

from __future__ import annotations

import logging
import os
import socket
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

import engine
from server import auth as amr_auth
from server import desktop as amr_desktop
from server import security as amr_security
from server.routes import register_routes

# Built frontend output (from ``frontend/`` via ``npm run build``). When present
# it is served at "/" (API routes registered above win over the static mount).
_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


class SPAStaticFiles(StaticFiles):
    """Static files with ``index.html`` fallback for client-side routes.

    The React router owns paths like ``/settings`` or ``/analysis`` that have no
    file behind them. Such extension-less, non-``/api`` paths are answered with
    ``index.html``; real files win, while missing assets (``/assets/x.js``) and
    unknown API paths keep their 404.
    """

    async def get_response(self, path: str, scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or not self._is_spa_route(path):
                raise
        return await super().get_response("index.html", scope)

    @staticmethod
    def _is_spa_route(path: str) -> bool:
        segments = path.replace("\\", "/").split("/")
        if segments[0] == "api":
            return False
        return not Path(segments[-1]).suffix


# Seconds to wait for a freshly spawned llama-server to answer its health probe.
_LLAMACPP_WARMUP_TIMEOUT = 120


def should_autostart_llamacpp() -> bool:
    """Return True when this install expects a *local* llama.cpp server.

    Requires a configured GGUF that actually exists and a loopback API base
    URL. A remote server URL (or no model yet) means there is nothing for this
    process to start.
    """
    model_cfg = engine.config.get("model", {}) or {}
    llamacpp = model_cfg.get("llamacpp", {}) or {}
    gguf = str(llamacpp.get("gguf_path") or "").strip()
    if not gguf or not Path(gguf).is_file():
        return False
    try:
        host, _port = engine._llamacpp_host_port()
    except Exception:
        return False
    return host in ("127.0.0.1", "localhost", "::1")


def start_llamacpp_in_background() -> bool:
    """Warm up the local AI server without blocking startup.

    The desktop installer ships ``llama-server.exe``, so starting it here means
    the first analysis does not fail with "the server is not running". A missing
    binary or model just leaves it down; the analysis route already reports that
    with an actionable message. Returns True when a warm-up thread was started.
    """
    if not should_autostart_llamacpp():
        return False
    try:
        if engine._llamacpp_server_running():
            return False
    except Exception:
        pass

    def _warmup() -> None:
        log = logging.getLogger(__name__)
        try:
            if not engine.ensure_llamacpp_server(timeout=_LLAMACPP_WARMUP_TIMEOUT):
                log.warning(
                    "llama.cpp server did not start; analysis will report it"
                )
        except Exception:  # pragma: no cover - defensive
            log.warning("llama.cpp auto-start raised", exc_info=True)

    threading.Thread(target=_warmup, name="llamacpp-warmup", daemon=True).start()
    return True

# NOTE: Allowing all origins is acceptable for a local single-user tool driven
# from localhost. If you expose this server on a LAN (e.g. --host 0.0.0.0),
# restrict ``allow_origins`` to trusted frontend origins and enable auth
# (see server/auth.py, env AMR_AUTH_ENABLED=1). The config key
# ``server.cors_origins`` (a list) overrides this default when present.
CORS_ALLOW_ORIGINS = ["*"]


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(title="AI Media Renamer API", version=engine.VERSION)

    # CORS origins: prefer an explicit ``server.cors_origins`` list from config
    # when present, otherwise fall back to the open default.
    cfg_origins = engine.config.get("server", {}).get("cors_origins")
    allow_origins = cfg_origins if isinstance(cfg_origins, list) and cfg_origins else CORS_ALLOW_ORIGINS

    # NOTE: ``allow_credentials`` is intentionally False. The app authenticates
    # via bearer tokens (never cookies), so omitting credentials lets the
    # permissive ``Access-Control-Allow-Origin: *`` actually take effect for
    # cross-origin loads (e.g. when the UI is reached via ``localhost`` while the
    # API is bound to ``127.0.0.1``, or behind a reverse proxy). Starlette only
    # emits a wildcard ACAO when credentials are disabled; with credentials
    # enabled a literal ``*`` origin list silently fails to echo the caller's
    # origin and every cross-origin fetch is blocked by the browser.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=False,
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

    if amr_desktop.desktop_mode():
        # Desktop boundary: every /api/* request needs the shell token (except
        # /health and the unregistered token issuer), and mutating requests must
        # come from a loopback Host/Origin. The shell never gets a second LAN
        # auth path.
        @app.middleware("http")
        async def _desktop_guard(request, call_next):
            if amr_desktop.is_desktop_request(request.url.path, request.method, request):
                if not amr_desktop.ws_token_ok(amr_desktop.bearer_token(request)):
                    return JSONResponse({"detail": "Unauthorized"}, status_code=401)
                if request.method in amr_desktop.MUTATING_METHODS:
                    if not amr_desktop.host_allowed(request) or not amr_desktop.origin_allowed(request):
                        return JSONResponse({"detail": "Forbidden"}, status_code=403)
            return await call_next(request)

        # The LAN token issuer does not exist in desktop mode. Register an
        # explicit 404 so the static catch-all cannot answer with a 405.
        @app.api_route(
            "/api/auth/token",
            methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            include_in_schema=False,
        )
        def _auth_token_not_found() -> None:
            raise HTTPException(status_code=404, detail="Not Found")
    else:
        # LAN-mode auth token issuer. When auth is disabled this reports the
        # state without issuing a token so clients can detect the mode.
        @app.post("/api/auth/token", tags=["auth"])
        def auth_token() -> dict:
            if not amr_auth.AUTH_ENABLED:
                return {"enabled": False}
            return {"enabled": True, "token": amr_auth.create_access_token({})}

    @app.on_event("startup")
    def _startup() -> None:
        # Ensure the engine config is loaded and environment probes are usable.
        engine.load_config(quiet=True)
        try:
            # Migrate any legacy GGUF cache before a server/model is requested.
            engine.start_model_migration()
            # Best-effort: confirm the environment check runs without raising.
            engine.check_environment()
        except Exception:
            pass
        # Bring the bundled local AI server up in the background so the first
        # analysis does not fail on a cold install.
        try:
            start_llamacpp_in_background()
        except Exception:
            logging.getLogger(__name__).warning(
                "llama.cpp auto-start could not be scheduled", exc_info=True
            )

    @app.on_event("shutdown")
    def _shutdown() -> None:
        # Only stops a server this process started; an externally launched
        # llama-server is left alone.
        try:
            engine.stop_llamacpp_server()
        except Exception:
            pass

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        return {
            "status": "ok",
            "version": engine.VERSION,
            "desktop": amr_desktop.desktop_mode(),
        }

    # Serve the built React frontend LAST so API routes and /health (registered
    # above) match first and are not swallowed by the catch-all mount.
    if _DIST.is_dir():
        app.mount("/", SPAStaticFiles(directory=str(_DIST), html=True), name="frontend")

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

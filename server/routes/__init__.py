"""Route registration — mount every router onto the FastAPI app."""

from __future__ import annotations

from fastapi import FastAPI

from server.routes import analysis, assets, browse, commit, config, environment, models, sessions, staging, updates


def register_routes(app: FastAPI) -> None:
    """Include all route routers into ``app``."""
    app.include_router(environment.router)
    app.include_router(config.router)
    app.include_router(browse.router)
    app.include_router(assets.router)
    app.include_router(analysis.router)
    app.include_router(staging.router)
    app.include_router(commit.router)
    app.include_router(sessions.router)
    app.include_router(models.router)
    app.include_router(updates.router)

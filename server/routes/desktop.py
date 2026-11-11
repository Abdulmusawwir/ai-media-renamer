"""Desktop shell support routes: authoritative busy state and shutdown."""

from __future__ import annotations

from fastapi import APIRouter

import engine
import server.routes.models as models_routes
from server import deps, desktop

router = APIRouter(prefix="/api", tags=["desktop"])


@router.get("/desktop/status")
def desktop_status() -> dict:
    """Return the single source of truth for busy state.

    The SPA must poll this instead of tracking its own child state. ``setup_running``
    is always False server-side; the desktop shell owns child setup state.
    """
    return {
        "analysis_running": deps.analysis_running(),
        "commit_running": deps.commit_running(),
        "model_downloads_running": models_routes.models_active_downloads(),
        "model_migration_running": bool(engine.is_model_migration_running()),
        "setup_running": False,
        "staging_count": len(deps.get_active_staging()),
    }


@router.post("/desktop/shutdown")
def desktop_shutdown() -> dict:
    """Stop llama-server and exit the process from a short background task."""
    desktop.begin_shutdown()
    return {"ok": True}

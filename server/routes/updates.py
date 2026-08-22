"""GET /api/updates/check — stub update check (no update mechanism yet)."""

from __future__ import annotations

from fastapi import APIRouter

import engine

router = APIRouter(prefix="/api", tags=["updates"])


@router.get("/updates/check")
def check_updates() -> dict:
    """Return a stub update-availability response.

    No update/auto-update mechanism exists in v2 yet; this endpoint is a
    placeholder so the frontend can ship the call without branching.
    """
    return {
        "update_available": False,
        "current_version": engine.VERSION,
    }

"""GET /api/environment — report tool and service availability."""

from __future__ import annotations

from fastapi import APIRouter, Depends

import engine
from server import deps

router = APIRouter(prefix="/api", tags=["environment"])


@router.get("/environment", dependencies=[Depends(deps.require_auth)])
def get_environment() -> dict:
    """Return the engine environment check (ffmpeg/exiftool/llamacpp/models)."""
    return engine.check_environment()

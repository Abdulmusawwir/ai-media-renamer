"""GET /api/environment — report tool and service availability."""

from __future__ import annotations

from fastapi import APIRouter

import engine

router = APIRouter(prefix="/api", tags=["environment"])


@router.get("/environment")
def get_environment() -> dict:
    """Return the engine environment check (ffmpeg/exiftool/llamacpp/models)."""
    return engine.check_environment()

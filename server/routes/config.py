"""GET/PUT /api/config — read and patch the engine configuration."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

import engine
from server import deps
from server.schemas import ConfigPutRequest

router = APIRouter(prefix="/api", tags=["config"])


@router.get("/config")
def get_config() -> dict:
    """Return the current config with sensitive keys stripped."""
    return deps.get_engine_config()


@router.put("/config", dependencies=[Depends(deps.require_auth)])
def put_config(req: ConfigPutRequest) -> dict:
    """Merge a partial config patch, persist it, then reload from disk."""
    patch = req.patch
    if not isinstance(patch, dict):
        raise HTTPException(status_code=400, detail="patch must be an object")

    config = engine.config
    _deep_merge(config, patch)

    try:
        engine.save_config()
        engine.reload_config()
    except Exception as exc:  # pragma: no cover - surface config write failures
        raise HTTPException(status_code=500, detail=f"failed to save config: {exc}")

    return deps.get_engine_config()


def _deep_merge(base: dict, override: dict) -> None:
    """Recursively merge ``override`` into ``base`` in place."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value

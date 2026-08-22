"""GET/DELETE /api/assets — inspect and remove staged assets."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from server import deps

router = APIRouter(prefix="/api", tags=["assets"])


@router.get("/assets")
def get_assets() -> dict:
    """Return the current in-memory staging list."""
    return {"assets": deps.get_active_staging(), "count": len(deps.ACTIVE_STAGING)}


@router.delete("/assets/{name}", dependencies=[Depends(deps.require_auth)])
def delete_asset(name: str) -> dict:
    """Remove a single staged asset by its ``original_name``."""
    before = len(deps.ACTIVE_STAGING)
    kept = [a for a in deps.ACTIVE_STAGING if a.get("original_name") != name]
    if len(kept) == before:
        raise HTTPException(status_code=404, detail="asset not found in staging")
    deps.set_active_staging(kept)
    return {"removed": name, "count": len(deps.ACTIVE_STAGING)}

"""Staging CRUD + bulk edit + CSV export/import."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

import engine
from server import deps
from server.schemas import StagingBulkRequest, StagingImportRequest

router = APIRouter(prefix="/api", tags=["staging"])


@router.get("/staging")
def get_staging() -> dict:
    """Return the current staging list."""
    return {"assets": deps.get_active_staging(), "count": len(deps.ACTIVE_STAGING)}


@router.put("/staging", dependencies=[Depends(deps.require_auth)])
def put_staging(assets: list[dict]) -> dict:
    """Replace the entire staging list."""
    if not isinstance(assets, list):
        raise HTTPException(status_code=400, detail="assets must be a list")
    # Ensure original_path strings are preserved as-is (engine expects str/Path).
    deps.set_active_staging(assets)
    return {"count": len(deps.ACTIVE_STAGING)}


@router.post("/staging/bulk", dependencies=[Depends(deps.require_auth)])
def bulk_edit(req: StagingBulkRequest) -> dict:
    """Apply ``updates`` to every staged asset whose name is in ``selected``."""
    if not req.selected:
        raise HTTPException(status_code=400, detail="no rows selected")
    selected = set(req.selected)
    applied = 0
    for asset in deps.ACTIVE_STAGING:
        if asset.get("original_name") in selected:
            for key, value in req.updates.items():
                if key in asset:
                    asset[key] = value
            applied += 1
    return {"applied": applied}


@router.get("/staging/export")
def export_staging() -> PlainTextResponse:
    """Return the staging list serialized as CSV text."""
    csv_text = engine.export_staging_csv(deps.ACTIVE_STAGING)
    return PlainTextResponse(csv_text, media_type="text/csv")


@router.post("/staging/import", dependencies=[Depends(deps.require_auth)])
def import_staging(req: StagingImportRequest) -> dict:
    """Import staging from CSV text (``{csv: "..."}``)."""
    csv_text = req.csv
    if not csv_text:
        raise HTTPException(status_code=400, detail="missing csv field")
    imported, warnings = engine.import_staging_csv(csv_text, engine.ALLOWED_CATEGORIES)
    staged = []
    for a in imported:
        staged.append(
            {
                "original_path": "",
                "original_name": a["original_name"],
                "staged_name": a["staged_name"],
                "category": a["category"],
                "tags": a["tags"],
                "summary": a.get("summary", ""),
                "topic": "",
                "description": "",
                "base64_data": "",
                "audio_transcription": "",
                "commit_status": "pending",
            }
        )
    deps.set_active_staging(staged)
    return {"imported": len(staged), "warnings": warnings}

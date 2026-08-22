"""POST /api/commit and POST /api/rollback — persist staged assets to disk."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

import engine
from server import deps
from server.schemas import CommitRequest, RollbackRequest

router = APIRouter(prefix="/api", tags=["commit"])


def _prepare_assets(assets: list[dict]) -> list[dict]:
    """Return staging assets with ``original_path`` coerced to a Path.

    The in-memory staging keeps ``original_path`` as a string for JSON
    safety; the engine commit functions require a ``Path`` with ``.suffix``.
    """
    prepared = []
    for a in assets:
        asset = dict(a)
        op = a.get("original_path")
        if op:
            asset["original_path"] = Path(op)
        prepared.append(asset)
    return prepared


@router.post("/commit")
def commit(req: CommitRequest) -> dict:
    """Commit the provided (or active) staging set to ``target_dir``."""
    assets = req.assets if req.assets else deps.ACTIVE_STAGING
    if not assets:
        raise HTTPException(status_code=400, detail="no assets to commit")

    target = Path(req.target_dir)
    target.mkdir(parents=True, exist_ok=True)

    prepared = _prepare_assets(assets)
    exif = engine.ExifToolSession()
    try:
        results = engine.execute_commit_batch(
            prepared,
            target,
            req.sort_folders,
            exif,
            skip_rename=req.skip_rename,
            skip_metadata=req.skip_metadata,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"commit failed: {exc}")
    finally:
        try:
            exif.close()
        except Exception:
            pass

    # Reflect commit results back into the active staging set.
    result_strings = [str(r) for r in results]
    for asset, res in zip(assets, result_strings):
        if res.startswith("ERROR:"):
            asset["commit_status"] = "failed"
            asset["commit_error"] = res[len("ERROR:") :]
        else:
            asset["commit_status"] = "committed"
            asset["committed_path"] = res

    return {"committed": len(results), "results": result_strings}


@router.post("/rollback")
def rollback(req: RollbackRequest | None = None) -> dict:
    """Roll back the most recent commit batch."""
    try:
        result = engine.rollback_last_batch()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"rollback failed: {exc}")
    return result

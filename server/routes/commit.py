"""POST /api/commit and POST /api/rollback — persist staged assets to disk."""

from __future__ import annotations

import uuid
from collections import OrderedDict
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

import engine
from server import deps
from server.schemas import CommitRequest, RollbackRequest

router = APIRouter(prefix="/api", tags=["commit"])

_XMP_TAGS = ["XMP-dc:Title", "XMP-dc:Description", "Microsoft:Category", "XMP-dc:Subject"]
_VIDEO_TAGS = [
    "QuickTime:Title",
    "QuickTime:Description",
    "QuickTime:Comment",
    "QuickTime:Keywords",
    "Keys:Description",
    "Keys:Keywords",
]
_OTHER_TAGS = ["EXIF:XPTitle", "EXIF:XPKeywords", "Description", "Comment", "Keywords"]


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


def _injected_tags(original_path: Path) -> list[str]:
    """Return the metadata keys the commit pipeline writes for this file type."""
    tags = list(_XMP_TAGS)
    if original_path.suffix.lower() in engine.VIDEO_EXTENSIONS:
        tags.extend(_VIDEO_TAGS)
    else:
        tags.extend(_OTHER_TAGS)
    return tags


def _destination_groups(
    prepared: list[dict], target_dir: str | None
) -> OrderedDict[Path, list[int]]:
    """Group asset indexes by destination root.

    An explicit ``target_dir`` commits everything into one directory (the
    previous behavior). Without one, each asset is committed in place next
    to its original file, matching the CLI.
    """
    groups: OrderedDict[Path, list[int]] = OrderedDict()
    if target_dir:
        groups[Path(target_dir)] = list(range(len(prepared)))
        return groups
    for index, asset in enumerate(prepared):
        groups.setdefault(asset["original_path"].parent, []).append(index)
    return groups


@router.post("/commit", dependencies=[Depends(deps.require_auth)])
def commit(req: CommitRequest) -> dict:
    """Commit the provided (or active) staging set.

    With ``target_dir`` the files are moved into that directory; without
    one they are renamed in place inside their original folders.
    """
    assets = req.assets if req.assets else deps.ACTIVE_STAGING
    if not assets:
        raise HTTPException(status_code=400, detail="no assets to commit")

    prepared = _prepare_assets(assets)
    groups = _destination_groups(prepared, req.target_dir)
    ordered_results: list[str | Path | None] = [None] * len(prepared)
    undo_records: list[dict] = []

    exif = engine.ExifToolSession()
    try:
        for group_target, indexes in groups.items():
            target = group_target.resolve()
            target.mkdir(parents=True, exist_ok=True)
            batch = [prepared[i] for i in indexes]
            results = engine.execute_commit_batch(
                batch,
                target,
                req.sort_folders,
                exif,
                skip_rename=req.skip_rename,
                skip_metadata=req.skip_metadata,
            )
            for index, result in zip(indexes, results):
                ordered_results[index] = result
                result_text = str(result)
                if result_text.startswith("ERROR:"):
                    continue
                new_path = Path(result_text)
                if not new_path.is_absolute():
                    new_path = target / new_path
                asset = prepared[index]
                undo_records.append(
                    {
                        "original_path": str(asset["original_path"]),
                        "new_path": str(new_path.resolve()),
                        "original_name": asset.get("original_name") or asset["original_path"].name,
                        "new_name": asset.get("staged_name", ""),
                        "category": asset.get("category", ""),
                        "tags": asset.get("tags", []),
                        "injected_tags": [] if req.skip_metadata else _injected_tags(asset["original_path"]),
                    }
                )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"commit failed: {exc}")
    finally:
        try:
            exif.close()
        except Exception:
            pass

    if undo_records:
        engine.log_commit_batch(str(uuid.uuid4())[:12], str(req.target_dir or ""), undo_records)

    result_strings = [
        str(r) if r is not None else "ERROR:asset was not committed"
        for r in ordered_results
    ]

    # Reflect commit results back into the active staging set.
    for asset, res in zip(assets, result_strings):
        if res.startswith("ERROR:"):
            asset["commit_status"] = "failed"
            asset["commit_error"] = res[len("ERROR:") :]
        else:
            asset["commit_status"] = "committed"
            asset["committed_path"] = res

    committed = sum(1 for res in result_strings if not res.startswith("ERROR:"))
    return {"committed": committed, "results": result_strings}


@router.post("/rollback", dependencies=[Depends(deps.require_auth)])
def rollback(req: RollbackRequest | None = None) -> dict:
    """Roll back the most recent commit batch."""
    try:
        result = engine.rollback_last_batch()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"rollback failed: {exc}")
    return result

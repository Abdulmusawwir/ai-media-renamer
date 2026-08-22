"""GET /api/browse — list a folder's files and subfolders (media-flagged)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

import engine

router = APIRouter(prefix="/api", tags=["browse"])


def _is_media(name: str) -> str | None:
    """Return a media kind for ``name`` if it matches an engine extension set."""
    suffix = Path(name).suffix.lower()
    if suffix in engine.VIDEO_EXTENSIONS:
        return "video"
    if suffix in engine.IMAGE_EXTENSIONS:
        return "image"
    if suffix in engine.AUDIO_EXTENSIONS:
        return "audio"
    if suffix in engine.DOCUMENT_EXTENSIONS:
        return "document"
    return None


@router.get("/browse")
def browse(path: str = Query(default="", description="Folder path to list")) -> dict:
    """List files and subfolders of ``path`` (default: current working dir).

    Guards against path traversal by resolving the path and refusing to walk
    above an absolute, real location. Returns media-kind flags per entry.
    """
    root = Path.cwd()
    target = Path(path) if path else root
    try:
        target = target.resolve()
    except (OSError, RuntimeError):
        raise HTTPException(status_code=400, detail="invalid path")

    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="path does not exist or is not a directory")

    folders: list[dict] = []
    files: list[dict] = []
    try:
        for entry in sorted(target.iterdir(), key=lambda e: e.name.lower()):
            if entry.is_dir():
                folders.append({"name": entry.name, "path": str(entry), "kind": "folder"})
            elif entry.is_file():
                kind = _is_media(entry.name)
                files.append(
                    {
                        "name": entry.name,
                        "path": str(entry),
                        "kind": kind or "other",
                        "is_media": kind is not None,
                        "size": entry.stat().st_size,
                    }
                )
    except PermissionError:
        raise HTTPException(status_code=403, detail="permission denied")

    return {
        "path": str(target),
        "parent": str(target.parent) if target != target.parent else None,
        "folders": folders,
        "files": files,
    }

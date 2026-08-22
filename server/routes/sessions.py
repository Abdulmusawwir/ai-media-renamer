"""GET/POST/DELETE /api/sessions — session persistence helpers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

import engine
from server import deps
from server.schemas import SessionCreateRequest

router = APIRouter(prefix="/api", tags=["sessions"])

SESSION_DIR = engine.SESSION_DIR


@router.get("/sessions")
def list_sessions() -> dict:
    """List saved session files (newest first)."""
    sessions = engine.list_sessions()
    # ``path`` is a Path; serialize to str for JSON.
    serialized = [
        {**{k: v for k, v in s.items() if k != "path"}, "path": str(s["path"])}
        for s in sessions
    ]
    return {"sessions": serialized}


@router.post("/sessions", dependencies=[Depends(deps.require_auth)])
def create_session(req: SessionCreateRequest) -> dict:
    """Save the current staging set as a session file."""
    if not deps.ACTIVE_STAGING:
        raise HTTPException(status_code=400, detail="no active staging to save")
    path = engine.save_session(deps.ACTIVE_STAGING, {}, req.settings)
    return {"saved": True, "path": str(path)}


@router.get("/sessions/{session_id}")
def load_session_by_id(session_id: str) -> dict:
    """Load a session by its filename (e.g. ``session_2026-01-01_120000.json``)."""
    candidate = SESSION_DIR / session_id
    try:
        data = engine.load_session(candidate)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"session not found: {exc}")
    staged = data.get("staged_assets", [])
    deps.set_active_staging(staged)
    return {"loaded": session_id, "asset_count": len(staged)}


@router.delete("/sessions/{session_id}", dependencies=[Depends(deps.require_auth)])
def delete_session_by_id(session_id: str) -> dict:
    """Delete a saved session file."""
    candidate = SESSION_DIR / session_id
    ok = engine.delete_session(candidate)
    if not ok:
        raise HTTPException(status_code=404, detail="session not found")
    return {"deleted": session_id}

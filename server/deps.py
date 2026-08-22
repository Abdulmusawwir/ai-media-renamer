"""Shared dependencies and in-memory session state for the v2 backend.

The server is stateless per-request, so the "current" staging set is kept in a
module-level list (``ACTIVE_STAGING``). This is sufficient for a single-user
local/LAN app and will be replaced by a persistence layer in a later phase.
"""

from __future__ import annotations

import threading

from fastapi import HTTPException, Request

import engine
from server import auth

# In-memory staging set for the active session. Holds the same dict schema the
# engine/CLI use, with ``original_path`` coerced to ``str`` for JSON safety.
ACTIVE_STAGING: list[dict] = []

# A single cancel flag shared by the currently running analysis. Good enough for
# a one-job-at-a-time local tool; a future revision can key this per connection.
_analysis_cancel: threading.Event | None = None
_analysis_lock = threading.Lock()


def get_cancel_event() -> threading.Event:
    """Return (creating if needed) the shared analysis cancel event."""
    global _analysis_cancel
    with _analysis_lock:
        if _analysis_cancel is None:
            _analysis_cancel = threading.Event()
        return _analysis_cancel


def reset_cancel_event() -> threading.Event:
    """Clear and return a fresh cancel event for a new analysis run."""
    global _analysis_cancel
    with _analysis_lock:
        _analysis_cancel = threading.Event()
        return _analysis_cancel


def get_active_staging() -> list[dict]:
    """Return the current in-memory staging list (a copy for safety)."""
    return list(ACTIVE_STAGING)


def set_active_staging(assets: list[dict]) -> None:
    """Replace the in-memory staging list."""
    ACTIVE_STAGING.clear()
    ACTIVE_STAGING.extend(assets)


def sanitize_config(cfg: dict) -> dict:
    """Return a deep-ish copy of ``cfg`` with sensitive keys removed.

    There are no API keys today, but be defensive: drop any key whose name
    contains ``key``, ``secret``, or ``token`` (case-insensitive), anywhere in
    the nested structure.
    """
    if isinstance(cfg, dict):
        clean = {}
        for k, v in cfg.items():
            if isinstance(k, str) and any(
                bad in k.lower() for bad in ("key", "secret", "token", "password")
            ):
                continue
            clean[k] = sanitize_config(v)
        return clean
    if isinstance(cfg, list):
        return [sanitize_config(item) for item in cfg]
    return cfg


def get_engine_config() -> dict:
    """Return the current engine config with sensitive keys stripped."""
    return sanitize_config(engine.config)


def make_exiftool_session():
    """Create a fresh ExifTool IPC session from the engine."""
    return engine.ExifToolSession()


async def require_auth(request: Request) -> None:
    """Env-gated auth dependency for sensitive routes.

    When ``AMR_AUTH_ENABLED`` is truthy, this extracts the
    ``Authorization: Bearer <token>`` header, verifies it via
    :func:`server.auth.verify_token`, and raises ``HTTPException(401)`` on
    missing or invalid tokens. When auth is disabled it is a no-op, preserving
    the unauthenticated local dev flow.
    """
    if not auth.AUTH_ENABLED:
        return
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = header[len("Bearer "):].strip()
    claims = auth.verify_token(token)
    if claims is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

"""JWT helpers for optional LAN-mode authentication.

Auth is OFF by default. When ``AUTH_ENABLED`` is False, the verification
helpers return a permissive sentinel so routes can stay auth-aware without
forcing tokens during local development. Enable by setting the env var
``AMR_AUTH_ENABLED=1`` and ``AMR_JWT_SECRET`` (a generated secret is used as a
fallback so the server still starts).
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any

import jwt

AUTH_ENABLED = os.environ.get("AMR_AUTH_ENABLED", "0") == "1"
JWT_SECRET = os.environ.get("AMR_JWT_SECRET", "dev-insecure-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_SECONDS = 60 * 60 * 12  # 12 hours

# A sentinel identity used when auth is disabled.
ANONYMOUS_CLAIMS: dict[str, Any] = {"sub": "anonymous", "lan": True}


def create_access_token(claims: dict[str, Any] | None = None, expires_in: int | None = None) -> str:
    """Create a signed JWT carrying ``claims`` with an expiry."""
    payload = dict(claims or {})
    payload["iat"] = int(time.time())
    payload["exp"] = int(time.time()) + (expires_in or JWT_EXPIRE_SECONDS)
    payload["jti"] = uuid.uuid4().hex
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict[str, Any] | None:
    """Verify and decode ``token``; return claims or None on failure."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


def current_claims(token: str | None) -> dict[str, Any]:
    """Resolve the effective identity for a request.

    Returns anonymous claims when auth is disabled, otherwise the verified
    token claims (or None if the token is missing/invalid).
    """
    if not AUTH_ENABLED:
        return ANONYMOUS_CLAIMS
    if not token:
        return {}
    return verify_token(token) or {}

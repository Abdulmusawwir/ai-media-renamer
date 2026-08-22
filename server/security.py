"""Optional per-IP rate-limiting middleware for the v2 backend.

Enabled only when the ``AMR_RATE_LIMIT`` environment variable is a positive
integer (requests per minute per client IP). When unset or invalid, the
middleware is never installed by ``server/main.py`` and the server behaves as
before. This is deliberately minimal — a single-user local/LAN tool does not
need a distributed limiter.
"""

from __future__ import annotations

import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

_WINDOW_SECONDS = 60


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Reject clients exceeding ``max_requests`` in a rolling 60s window."""

    def __init__(self, app, max_requests: int) -> None:
        super().__init__(app)
        self.max_requests = max_requests
        self._hits: dict[str, list[float]] = defaultdict(list)

    def _client_ip(self, request: Request) -> str:
        if request.client is not None:
            return request.client.host
        return request.headers.get("X-Forwarded-For", "unknown").split(",")[0].strip()

    async def dispatch(self, request: Request, call_next):
        ip = self._client_ip(request)
        now = time.time()

        window = self._hits[ip]
        # Evict timestamps older than the rolling window.
        while window and window[0] <= now - _WINDOW_SECONDS:
            window.pop(0)

        if len(window) >= self.max_requests:
            return JSONResponse(
                status_code=429,
                content={"error": "rate limit exceeded", "retry_after_seconds": _WINDOW_SECONDS},
            )

        window.append(now)
        return await call_next(request)

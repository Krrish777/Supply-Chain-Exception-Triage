"""Rate-limit middleware stub.

Real implementation is Sprint 4 scope (tracked in Sprint 0 PRD v2 §2.4 + §3).
Sprint 0 ships the stub so that the canonical middleware stack documented in
``main.py::create_app()`` has a stable module path — callers don't have to
conditionally add the middleware when it lands in Sprint 4.

TODO(sprint-4): implement token-bucket or sliding-window rate limiting backed
by Redis or Firestore. Pair with Firebase custom claims for per-tenant quotas.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
    from starlette.responses import Response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Pass-through stub. Real enforcement lands in Sprint 4."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """No-op: Sprint 0 ships the shape, Sprint 4 adds enforcement."""
        return await call_next(request)

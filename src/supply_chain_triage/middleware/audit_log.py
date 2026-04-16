"""Audit logging middleware and ``audit_event`` helper.

Binds a per-request ``correlation_id`` into structlog contextvars so every
request log line carries the same request ID.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware

from supply_chain_triage.utils.logging import (
    generate_request_id,
    get_logger,
    request_id_var,
)

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
    from starlette.responses import Response


_logger = get_logger("audit")


def audit_event(event: str, **kwargs: Any) -> None:
    """Emit a structured audit event through the canonical logger."""
    _logger.info(event, **kwargs)


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Wrap every request with a ``correlation_id`` and start/end audit events."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Bind correlation_id to contextvars + emit request.start/.end audits."""
        correlation_id = generate_request_id()
        request.state.correlation_id = correlation_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            correlation_id=correlation_id,
            request_id=correlation_id,
        )
        request_id_token = request_id_var.set(correlation_id)

        audit_event(
            "request.start",
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
        )

        try:
            response = await call_next(request)
        except Exception:  # pragma: no cover — emit audit then re-raise
            audit_event(
                "request.error",
                correlation_id=correlation_id,
                method=request.method,
                path=request.url.path,
            )
            raise
        finally:
            request_id_var.reset(request_id_token)

        audit_event(
            "request.end",
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
            status=response.status_code,
        )
        response.headers["X-Correlation-Id"] = correlation_id
        return response

"""Audit logging middleware + module-level `audit_event` helper.

Emits structured JSON via the project's canonical logger
(``supply_chain_triage.utils.logging.get_logger``) with a per-request
``correlation_id`` bound through ``structlog.contextvars``. AuditLogMiddleware
wraps every request — including auth failures. The Risk 11 regression guard
(test-plan Test 4.2) verifies that when FirebaseAuthMiddleware returns 401,
the audit log still carries a ``correlation_id``. If this guard breaks, it
means someone re-ordered the middleware stack so AuditLog is no longer
outermost.

Canonical middleware ordering in ``main.py::create_app()``:

    add_cors_middleware(app, ...)        # first added → INNERMOST
    app.add_middleware(InputSanitizationMiddleware)
    app.add_middleware(FirebaseAuthMiddleware, ...)
    app.add_middleware(AuditLogMiddleware) # last added → OUTERMOST

``audit_event`` is a module-level helper so tools / runners / agents can emit
structured audit lines outside the HTTP middleware context.
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
    """Emit a structured audit event.

    Usable from anywhere — tools, agents, runners, middleware. The resulting
    log line is a JSON object with ``event=<event>`` plus all kwargs, routed
    through ``utils.logging.get_logger`` so PII redaction, request_id merge,
    and the stdlib-bridged handlers all apply uniformly.

    Args:
        event: Event name (e.g. ``"shipment.read"``, ``"auth.failure"``).
        **kwargs: Structured context — ``correlation_id``, ``user_id``,
            ``company_id``, ``exception_id``, etc. Never pass raw prompt
            text or secrets (``.claude/rules/observability.md`` §5).
    """
    _logger.info(event, **kwargs)


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Wraps every request with a ``correlation_id`` + start/end audit events.

    Binds ``correlation_id`` via ``structlog.contextvars`` so every downstream
    ``get_logger(...).info(...)`` call in the same request carries it
    automatically — no manual threading. Also sets the raw ``request_id_var``
    for stdlib-compat with uvicorn access logs. See
    ``docs/research/Supply-Chain-Zettel-Structlog-Async-Contextvars``.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Bind correlation_id to contextvars + emit request.start/.end audits."""
        correlation_id = generate_request_id()
        request.state.correlation_id = correlation_id

        # Fresh per-request contextvars (Starlette may reuse async tasks).
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            correlation_id=correlation_id,
            request_id=correlation_id,
        )
        # Stdlib-compat: uvicorn access logs read from the raw ContextVar.
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

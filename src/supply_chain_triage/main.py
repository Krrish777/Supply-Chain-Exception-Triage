"""FastAPI application factory and CLI entry point.

The middleware stack must stay in the documented order so audit logging wraps
auth failures and request sanitization runs before handlers.
"""

from __future__ import annotations

from fastapi import FastAPI

from supply_chain_triage.core.config import get_settings
from supply_chain_triage.middleware.audit_log import AuditLogMiddleware
from supply_chain_triage.middleware.cors import add_cors_middleware
from supply_chain_triage.middleware.firebase_auth import FirebaseAuthMiddleware
from supply_chain_triage.middleware.input_sanitization import InputSanitizationMiddleware
from supply_chain_triage.runners.routes.triage import router as triage_router

# Paths that bypass Firebase Auth. Keep this list short + explicit.
_PUBLIC_PATHS: frozenset[str] = frozenset(
    {"/health", "/docs", "/openapi.json", "/redoc"},
)


def create_app() -> FastAPI:
    """Build the FastAPI app with the canonical middleware stack.

    The order is load-bearing: CORS runs closest to handlers, then input
    sanitization, then Firebase auth, and AuditLog stays outermost so 401s
    still emit a ``correlation_id``.
    """
    app = FastAPI(
        title="Supply Chain Exception Triage",
        description=(
            "AI-powered exception triage for small 3PLs. Sprint 0 ships the "
            "skeleton; feature agents land Sprints 1-3."
        ),
        version="0.1.0-sprint-0",
    )

    settings = get_settings()

    # INNERMOST first (Starlette LIFO — closest to handlers).
    add_cors_middleware(app, allowed_origins=settings.cors_allowed_origins)
    app.add_middleware(InputSanitizationMiddleware)
    app.add_middleware(FirebaseAuthMiddleware, public_paths=_PUBLIC_PATHS)
    app.add_middleware(AuditLogMiddleware)  # OUTERMOST — must stay last.

    app.include_router(triage_router)

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        """Public liveness probe. Never requires auth."""
        return {"status": "ok"}

    return app


def cli() -> None:
    """Console-script entry point. Starts uvicorn on port 8000."""
    import uvicorn

    uvicorn.run(
        "supply_chain_triage.main:create_app",
        factory=True,
        host="0.0.0.0",  # noqa: S104 — dev default; Cloud Run sets PORT
        port=8000,
        reload=False,
    )

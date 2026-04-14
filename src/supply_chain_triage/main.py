"""FastAPI application factory + CLI entry point.

Wired per Sprint 0 PRD v2 §7. The canonical middleware order is documented
inline below — reordering the ``add_middleware`` calls causes Risk 11 (401
responses skip the audit log). Test 4.2 is the regression guard.

CLI entry: ``supply-chain-triage`` (declared in ``pyproject.toml``) → ``cli()``.
"""

from __future__ import annotations

from fastapi import FastAPI

from supply_chain_triage.core.config import get_settings
from supply_chain_triage.middleware.audit_log import AuditLogMiddleware
from supply_chain_triage.middleware.cors import add_cors_middleware
from supply_chain_triage.middleware.firebase_auth import FirebaseAuthMiddleware
from supply_chain_triage.middleware.input_sanitization import InputSanitizationMiddleware

# Paths that bypass Firebase Auth. Keep this list short + explicit.
_PUBLIC_PATHS: frozenset[str] = frozenset(
    {"/health", "/docs", "/openapi.json", "/redoc"},
)


def create_app() -> FastAPI:
    """Build the FastAPI app with the canonical middleware stack.

    **Middleware ordering is load-bearing (Risk 11).** Starlette applies
    middleware in LIFO order — the LAST ``add_middleware`` call becomes the
    OUTERMOST wrapper on the request. We require ``AuditLogMiddleware`` to
    be outermost so every response (including 401s from
    ``FirebaseAuthMiddleware``) carries a ``correlation_id`` in its audit
    trail. Test 4.2 in the Sprint 0 test-plan is the regression guard.

    **Canonical order (outer → inner as each request flows in):**

    1. ``AuditLogMiddleware`` — first to see every request; last to see
       every response. Generates ``correlation_id``.
    2. ``FirebaseAuthMiddleware`` — rejects unauthenticated requests
       (except ``_PUBLIC_PATHS``).
    3. ``InputSanitizationMiddleware`` — strips XSS + control chars before
       handlers read the body.
    4. ``CORSMiddleware`` (via ``add_cors_middleware``) — closest to
       handlers; handles preflight without auth.

    Do NOT reorder. If you add a new middleware, document its position in
    this comment block AND add a test that asserts ``correlation_id``
    survives the path.

    Returns:
        Configured FastAPI instance ready for uvicorn / ADK web.
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

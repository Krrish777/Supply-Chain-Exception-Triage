"""Firebase Auth middleware.

Verifies Firebase ID tokens using the first-party ``firebase-admin`` SDK
(Resolved Decision #4 in Sprint 0 PRD). Attaches ``uid``, ``email``, and the
``company_id`` custom claim to ``request.state`` for downstream handlers.

Multi-tenant isolation anchor: if the verified token does not carry a
``company_id`` custom claim, the request is rejected with 403. This forces
every authenticated request to be scoped to exactly one tenant. See
``docs/research/zettel-firestore-multi-tenant.md``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.responses import JSONResponse
from firebase_admin import auth as firebase_auth
from starlette.middleware.base import BaseHTTPMiddleware

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
    from starlette.responses import Response


class FirebaseAuthMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that verifies Firebase ID tokens."""

    def __init__(
        self,
        app: object,
        public_paths: frozenset[str] = frozenset(),
    ) -> None:
        """Initialize with an optional allowlist of unauthenticated paths.

        Args:
            app: The ASGI app to wrap.
            public_paths: Paths that skip auth entirely (health checks, docs).
        """
        super().__init__(app)  # type: ignore[arg-type]
        self.public_paths = public_paths

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Verify the Firebase ID token and attach claims to request.state."""
        if request.url.path in self.public_paths:
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        if not auth_header.lower().startswith("bearer "):
            return JSONResponse({"error": "missing_credentials"}, status_code=401)

        token = auth_header.split(" ", 1)[1].strip()
        try:
            claims = firebase_auth.verify_id_token(token)
        except firebase_auth.ExpiredIdTokenError:
            return JSONResponse({"error": "token_expired"}, status_code=401)
        except firebase_auth.InvalidIdTokenError:
            return JSONResponse({"error": "invalid_signature"}, status_code=401)
        except Exception:
            return JSONResponse({"error": "invalid_token"}, status_code=401)

        company_id = claims.get("company_id")
        if not company_id:
            return JSONResponse({"error": "missing_company_claim"}, status_code=403)

        request.state.user_id = claims.get("uid")
        request.state.company_id = company_id
        request.state.email = claims.get("email")
        return await call_next(request)

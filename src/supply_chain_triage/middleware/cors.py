"""CORS middleware helper.

Rejects wildcard origins (``"*"``) at startup to prevent accidental open-CORS
in production. Security posture: explicit allowlist only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.middleware.cors import CORSMiddleware

if TYPE_CHECKING:  # pragma: no cover
    from fastapi import FastAPI


def add_cors_middleware(app: FastAPI, allowed_origins: list[str]) -> None:
    """Attach CORS middleware to ``app`` with an explicit origin allowlist.

    Args:
        app: FastAPI application.
        allowed_origins: Exact origin strings. Wildcards are rejected.

    Raises:
        ValueError: If any origin is ``"*"`` (wildcard). Tighten the allowlist.
    """
    if any(origin == "*" for origin in allowed_origins):
        raise ValueError(
            "CORS wildcard '*' is not permitted — provide an explicit origin allowlist."
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

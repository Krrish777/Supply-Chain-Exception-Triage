"""CORS middleware tests (test-plan Area 7, tests 7.1–7.2)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from supply_chain_triage.middleware.cors import add_cors_middleware


class TestCorsAllowedOrigin:
    def test_allowed_origin_passes_preflight(self) -> None:
        # Given: FastAPI app with CORS allowlist ["http://localhost:3000"]
        app = FastAPI()
        add_cors_middleware(app, allowed_origins=["http://localhost:3000"])

        @app.get("/")
        def root() -> dict[str, object]:
            return {}

        client = TestClient(app)
        # When: OPTIONS with Origin: http://localhost:3000
        resp = client.options(
            "/",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        # Then: Access-Control-Allow-Origin header present and matches
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


class TestCorsDisallowedOrigin:
    def test_disallowed_origin_blocked(self) -> None:
        app = FastAPI()
        add_cors_middleware(app, allowed_origins=["http://localhost:3000"])

        @app.get("/")
        def root() -> dict[str, object]:
            return {}

        client = TestClient(app)
        resp = client.options(
            "/",
            headers={
                "Origin": "http://evil.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        # Then: ACAO either missing or explicitly not the evil origin
        assert resp.headers.get("access-control-allow-origin") != "http://evil.com"


class TestCorsWildcardRejected:
    def test_wildcard_rejected_at_startup(self) -> None:
        # Given: app + attempt to add wildcard origin
        app = FastAPI()
        # When / Then: ValueError raised at startup (bad config caught early)
        with pytest.raises(ValueError, match="wildcard"):
            add_cors_middleware(app, allowed_origins=["*"])

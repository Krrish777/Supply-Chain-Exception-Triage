"""Smoke tests for the FastAPI app factory (Sprint 0 PRD v2 §7 bootstrap)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from supply_chain_triage.main import create_app


@pytest.fixture
def app_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Build a test client with required env stubbed for Settings()."""
    monkeypatch.setenv("GCP_PROJECT_ID", "sct-test")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "sct-test-firebase")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", '["http://localhost:3000"]')
    # Reset Settings cache so the monkeypatched env is used.
    from supply_chain_triage.core.config import get_settings

    get_settings.cache_clear()
    return TestClient(create_app())


class TestHealthEndpoint:
    def test_health_is_public_and_returns_ok(self, app_client: TestClient) -> None:
        # Given: app with canonical middleware (FirebaseAuth active)
        # When: GET /health WITHOUT Authorization header
        resp = app_client.get("/health")
        # Then: /health is in _PUBLIC_PATHS → bypasses auth → 200
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestMiddlewareOrdering:
    """Risk 11 regression — AuditLog must be OUTERMOST in create_app()."""

    def test_audit_log_is_outermost_after_create_app(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Given: Settings env stubbed so create_app works.
        monkeypatch.setenv("GCP_PROJECT_ID", "sct-test")
        monkeypatch.setenv("FIREBASE_PROJECT_ID", "sct-test-firebase")
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", '["http://localhost:3000"]')
        from supply_chain_triage.core.config import get_settings

        get_settings.cache_clear()
        # When: create_app builds the stack
        app = create_app()
        # Then: app.user_middleware is stored in reverse-insertion order
        # (index 0 is what runs OUTERMOST on the request — the last-added).
        # AuditLogMiddleware was last added, so it must be at index 0.
        outermost_cls_name = app.user_middleware[0].cls.__name__
        assert outermost_cls_name == "AuditLogMiddleware", (
            f"Risk 11 regression: {outermost_cls_name} is outermost, not "
            f"AuditLogMiddleware. Auth failures (401) will skip audit logging. "
            f"Check create_app() in main.py — AuditLog must be the LAST "
            f"add_middleware call."
        )

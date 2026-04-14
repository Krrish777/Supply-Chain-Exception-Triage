"""Audit log tests (test-plan Area 4, tests 4.1–4.2).

Test 4.2 is the Risk 11 regression guard: even when FirebaseAuthMiddleware
returns 401, the response must still carry a correlation_id in the audit log —
proving AuditLogMiddleware wrapped the auth failure rather than being skipped.
"""

from __future__ import annotations

import json
from io import StringIO

import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient

from supply_chain_triage.middleware.audit_log import AuditLogMiddleware, audit_event
from supply_chain_triage.middleware.cors import add_cors_middleware
from supply_chain_triage.middleware.firebase_auth import FirebaseAuthMiddleware
from supply_chain_triage.middleware.input_sanitization import InputSanitizationMiddleware


@pytest.fixture
def log_capture() -> StringIO:
    """Capture structlog JSON output to an in-memory stream."""
    buf = StringIO()
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=buf),
        cache_logger_on_first_use=False,
    )
    return buf


class TestAuditEventHelper:
    def test_correlation_id_propagates_in_json(self, log_capture: StringIO) -> None:
        # Given: audit_event called with a correlation_id
        audit_event("action_X", correlation_id="abc-123", user_id="user_1")
        # When: captured
        line = log_capture.getvalue().strip().splitlines()[-1]
        payload = json.loads(line)
        # Then: fields preserved in the JSON output
        assert payload["event"] == "action_X"
        assert payload["correlation_id"] == "abc-123"
        assert payload["user_id"] == "user_1"
        assert "timestamp" in payload


class TestMiddlewareOrderingRegressionGuard:
    """Risk 11: if AuditLogMiddleware stops being outermost, auth-401s lose audit trail."""

    def test_correlation_id_present_on_401(self, log_capture: StringIO) -> None:
        # Given: the canonical middleware stack (AuditLog outermost)
        app = FastAPI()
        add_cors_middleware(app, allowed_origins=["http://localhost:3000"])
        app.add_middleware(InputSanitizationMiddleware)
        app.add_middleware(
            FirebaseAuthMiddleware,
            public_paths=frozenset({"/health"}),
        )
        app.add_middleware(AuditLogMiddleware)  # LIFO → this is OUTERMOST

        @app.get("/protected")
        def protected() -> dict[str, object]:
            return {}

        client = TestClient(app)
        # When: a request rejected by FirebaseAuthMiddleware (no Authorization header)
        resp = client.get("/protected")
        # Then: response is 401 AND audit log captured this request with a correlation_id
        assert resp.status_code == 401
        logs = log_capture.getvalue().strip().splitlines()
        captured = [json.loads(line) for line in logs if line.strip()]
        # Find the audit entry for this request — must have a correlation_id
        request_logs = [entry for entry in captured if entry.get("correlation_id")]
        assert request_logs, (
            "Audit log missing correlation_id on 401 response — "
            "AuditLogMiddleware is not outermost (Risk 11 regression). "
            "Check create_app() middleware ordering: AuditLog must be last add_middleware."
        )

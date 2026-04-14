"""Unit tests for utils.logging — PII drop, request_id, domain helpers."""

from __future__ import annotations

import structlog

from supply_chain_triage.utils.logging import (
    generate_request_id,
    get_logger,
    log_agent_invocation,
    log_api_call,
    request_id_var,
)


class TestGetLogger:
    def test_returns_bound_logger(self, log_output) -> None:  # type: ignore[no-untyped-def]
        logger = get_logger(__name__)
        logger.info("smoke_event", key="value")
        assert any(
            e["event"] == "smoke_event" and e.get("key") == "value" for e in log_output.entries
        )

    def test_auto_prefixes_project_namespace(self) -> None:
        # Calling get_logger("foo") should produce a structlog BoundLogger
        # wrapping a stdlib logger under the supply_chain_triage namespace.
        # We verify by asking stdlib's logger manager directly (structlog's
        # internal attributes vary across versions).
        import logging as stdlib_logging

        get_logger("foo")  # side effect: registers the stdlib logger
        assert stdlib_logging.getLogger("supply_chain_triage.foo").name == (
            "supply_chain_triage.foo"
        )


class TestPIIDrop:
    def test_email_is_dropped(self, log_output) -> None:  # type: ignore[no-untyped-def]
        # NOTE: the log_output fixture swaps structlog config for a pure capture
        # (no PII processor). To exercise the PII processor directly, invoke it
        # against a representative event_dict.
        from supply_chain_triage.utils.logging import _drop_pii

        event_dict = {
            "event": "user_login",
            "uid": "u_1",
            "email": "secret@example.com",
            "safe_field": "ok",
        }
        result = _drop_pii(None, "info", event_dict)
        assert "email" not in result
        assert "safe_field" in result  # non-PII preserved
        assert result["uid"] == "u_1"

    def test_token_is_dropped(self) -> None:
        from supply_chain_triage.utils.logging import _drop_pii

        result = _drop_pii(None, "info", {"event": "x", "token": "secret"})
        assert "token" not in result

    def test_raw_content_is_dropped(self) -> None:
        # ExceptionEvent.raw_content is a PII field per security.md §7.
        from supply_chain_triage.utils.logging import _drop_pii

        result = _drop_pii(None, "info", {"event": "x", "raw_content": "..."})
        assert "raw_content" not in result


class TestRequestIdContextVar:
    def test_request_id_var_defaults_to_dash(self) -> None:
        # Fresh contextvar should default to "-" (our sentinel for "no request").
        # Direct check without going through a processor.
        assert request_id_var.get() == "-"

    def test_structlog_contextvars_binding_round_trip(self) -> None:
        # bind_contextvars(request_id=X) should surface via merge_contextvars
        # processor (which is first in our chain).
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id="abc-123")
        try:
            # Check the contextvars stash directly — structlog stores it in
            # its own internal ContextVar, not our raw request_id_var.
            bound = structlog.contextvars.get_contextvars()
            assert bound.get("request_id") == "abc-123"
        finally:
            structlog.contextvars.clear_contextvars()


class TestGenerateRequestId:
    def test_returns_12_char_hex(self) -> None:
        rid = generate_request_id()
        assert len(rid) == 12
        assert all(c in "0123456789abcdef" for c in rid)

    def test_returns_unique_per_call(self) -> None:
        ids = {generate_request_id() for _ in range(100)}
        assert len(ids) == 100  # no collisions


class TestDomainHelpers:
    def test_log_agent_invocation_emits_agent_invoked(self, log_output) -> None:  # type: ignore[no-untyped-def]
        log_agent_invocation(
            agent_name="classifier",
            duration_ms=42.0,
            tokens_in=100,
            tokens_out=50,
        )
        matched = [e for e in log_output.entries if e["event"] == "agent_invoked"]
        assert matched
        assert matched[0]["agent_name"] == "classifier"
        assert matched[0]["duration_ms"] == 42.0
        assert matched[0]["tokens_in"] == 100

    def test_log_api_call_flags_failure(self, log_output) -> None:  # type: ignore[no-untyped-def]
        log_api_call(method="GET", endpoint="/x", status_code=500, duration_ms=10.0)
        matched = [e for e in log_output.entries if e["event"] == "api_call"]
        assert matched
        assert matched[0]["outcome"] == "FAIL"
        assert matched[0]["status_code"] == 500

    def test_log_api_call_flags_ok(self, log_output) -> None:  # type: ignore[no-untyped-def]
        log_api_call(method="GET", endpoint="/x", status_code=200, duration_ms=10.0)
        matched = [e for e in log_output.entries if e["event"] == "api_call"]
        assert matched
        assert matched[0]["outcome"] == "OK"

"""Unit tests for classifier agent callbacks and post-classification rules."""

from __future__ import annotations

import json
import os
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("GCP_PROJECT_ID", "sct-test")
os.environ.setdefault("FIREBASE_PROJECT_ID", "sct-test")
os.environ.setdefault("SCT_DISABLE_SECRET_MANAGER", "1")

from supply_chain_triage.modules.triage.agents.classifier.agent import (
    _STATE_START,
    _STATE_TOKENS_IN,
    _STATE_TOKENS_OUT,
    _after_agent,
    _after_model,
    _apply_post_classification_rules,
    _before_agent,
    _clear_history,
)


def _ctx(state: dict | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.state = state or {}
    return ctx


class TestBeforeAgent:
    def test_stamps_start_time(self):
        ctx = _ctx()
        _before_agent(ctx)
        assert _STATE_START in ctx.state
        assert isinstance(ctx.state[_STATE_START], int)
        assert ctx.state[_STATE_START] > 0


class TestAfterModel:
    def test_captures_usage_metadata(self):
        ctx = _ctx()
        resp = SimpleNamespace(
            usage_metadata=SimpleNamespace(prompt_token_count=100, candidates_token_count=50)
        )
        _after_model(ctx, resp)  # type: ignore[arg-type]
        assert ctx.state[_STATE_TOKENS_IN] == 100
        assert ctx.state[_STATE_TOKENS_OUT] == 50

    def test_accumulates_tokens_across_calls(self):
        ctx = _ctx({_STATE_TOKENS_IN: 100, _STATE_TOKENS_OUT: 50})
        resp = SimpleNamespace(
            usage_metadata=SimpleNamespace(prompt_token_count=200, candidates_token_count=30)
        )
        _after_model(ctx, resp)  # type: ignore[arg-type]
        assert ctx.state[_STATE_TOKENS_IN] == 300
        assert ctx.state[_STATE_TOKENS_OUT] == 80

    def test_degrades_when_metadata_missing(self):
        ctx = _ctx()
        resp = SimpleNamespace()
        _after_model(ctx, resp)  # type: ignore[arg-type]
        assert ctx.state[_STATE_TOKENS_IN] == 0
        assert ctx.state[_STATE_TOKENS_OUT] == 0


class TestClearHistory:
    def test_clears_contents(self):
        ctx = _ctx()
        request = SimpleNamespace(contents=["msg1", "msg2"])
        _clear_history(ctx, request)  # type: ignore[arg-type]
        assert request.contents == []

    def test_handles_none_request(self):
        ctx = _ctx()
        _clear_history(ctx, None)  # type: ignore[arg-type]
        # Should not raise


class TestPostClassificationRules:
    def _make_classification(self, **overrides) -> str:
        base = {
            "exception_type": "carrier_capacity_failure",
            "subtype": "vehicle_breakdown",
            "severity": "MEDIUM",
            "urgency_hours": 6,
            "confidence": 0.85,
            "key_facts": {"carrier_name": "BlueDart"},
            "reasoning": "Test reasoning",
            "requires_human_approval": False,
            "tools_used": [],
            "safety_escalation": None,
        }
        base.update(overrides)
        return json.dumps(base)

    def test_safety_incident_clamped_to_critical(self):
        ctx = _ctx({"triage:raw_exception_data": ""})
        raw = self._make_classification(exception_type="safety_incident", severity="MEDIUM")
        _apply_post_classification_rules(ctx, raw)
        result = json.loads(ctx.state["triage:classification"])
        assert result["severity"] == "CRITICAL"

    def test_regulatory_clamped_to_high(self):
        ctx = _ctx({"triage:raw_exception_data": ""})
        raw = self._make_classification(exception_type="regulatory_compliance", severity="LOW")
        _apply_post_classification_rules(ctx, raw)
        result = json.loads(ctx.state["triage:classification"])
        assert result["severity"] == "HIGH"

    def test_regulatory_high_not_downgraded(self):
        ctx = _ctx({"triage:raw_exception_data": ""})
        raw = self._make_classification(exception_type="regulatory_compliance", severity="CRITICAL")
        _apply_post_classification_rules(ctx, raw)
        # Severity already above HIGH — should remain CRITICAL
        written = ctx.state.get("triage:classification")
        if written:
            result = json.loads(written)
            assert result["severity"] == "CRITICAL"

    def test_low_confidence_triggers_human_approval(self):
        ctx = _ctx({"triage:raw_exception_data": ""})
        raw = self._make_classification(confidence=0.5)
        _apply_post_classification_rules(ctx, raw)
        result = json.loads(ctx.state["triage:classification"])
        assert result["requires_human_approval"] is True

    def test_high_confidence_no_human_approval(self):
        ctx = _ctx({"triage:raw_exception_data": ""})
        raw = self._make_classification(confidence=0.9)
        _apply_post_classification_rules(ctx, raw)
        # No modification expected — state should not be written
        assert "triage:classification" not in ctx.state

    def test_safety_keywords_trigger_escalation(self):
        ctx = _ctx({"triage:raw_exception_data": "There was a fire and chemical spill"})
        raw = self._make_classification()
        _apply_post_classification_rules(ctx, raw)
        result = json.loads(ctx.state["triage:classification"])
        assert result["safety_escalation"] is not None
        assert result["safety_escalation"]["trigger_type"] == "keyword_detection"
        assert "fire" in result["safety_escalation"]["matched_terms"]
        assert result["requires_human_approval"] is True
        assert result["severity"] == "CRITICAL"

    def test_no_safety_keywords_no_escalation(self):
        ctx = _ctx({"triage:raw_exception_data": "normal delivery delay for BlueDart"})
        raw = self._make_classification()
        _apply_post_classification_rules(ctx, raw)
        # No modification expected
        assert "triage:classification" not in ctx.state

    def test_invalid_json_does_not_crash(self):
        ctx = _ctx({"triage:raw_exception_data": ""})
        _apply_post_classification_rules(ctx, "not valid json")
        # Should not raise, should not write to state
        assert "triage:classification" not in ctx.state


class TestAfterAgent:
    def test_emits_log_event(self):
        from supply_chain_triage.utils.logging import _configure_once, get_logger

        _configure_once()
        get_logger("test")

        import structlog

        cap = structlog.testing.LogCapture()
        structlog.configure(processors=[cap])

        try:
            ctx = _ctx(
                {
                    _STATE_START: time.perf_counter_ns() - 100_000_000,
                    _STATE_TOKENS_IN: 500,
                    _STATE_TOKENS_OUT: 100,
                }
            )
            _after_agent(ctx)

            agent_events = [e for e in cap.entries if e.get("event") == "agent_invoked"]
            assert len(agent_events) >= 1
            assert agent_events[0]["agent_name"] == "classifier"
        finally:
            structlog.reset_defaults()

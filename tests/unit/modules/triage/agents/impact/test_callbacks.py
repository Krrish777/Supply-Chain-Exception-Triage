"""Unit tests for impact-agent callbacks and priority weight computation."""

from __future__ import annotations

import json
import os
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("GCP_PROJECT_ID", "sct-test")
os.environ.setdefault("FIREBASE_PROJECT_ID", "sct-test")
os.environ.setdefault("SCT_DISABLE_SECRET_MANAGER", "1")

from supply_chain_triage.modules.triage.agents.impact.agent import (
    _STATE_START,
    _STATE_TOKENS_IN,
    _STATE_TOKENS_OUT,
    _after_model,
    _apply_priority_weights,
    _before_agent,
    _clear_history,
)


def _make_callback_context(**state_overrides) -> MagicMock:
    ctx = MagicMock()
    ctx.state = dict(state_overrides)
    return ctx


# ---------------------------------------------------------------------------
# _before_agent
# ---------------------------------------------------------------------------


class TestBeforeAgent:
    def test_sets_perf_timer(self):
        ctx = _make_callback_context()
        _before_agent(ctx)

        assert _STATE_START in ctx.state
        assert isinstance(ctx.state[_STATE_START], int)
        assert ctx.state[_STATE_START] > 0

    def test_perf_timer_is_monotonic(self):
        before = time.perf_counter_ns()
        ctx = _make_callback_context()
        _before_agent(ctx)
        after = time.perf_counter_ns()

        assert before <= ctx.state[_STATE_START] <= after


# ---------------------------------------------------------------------------
# _after_model
# ---------------------------------------------------------------------------


class TestAfterModel:
    def test_accumulates_tokens(self):
        ctx = _make_callback_context()
        resp = SimpleNamespace(
            usage_metadata=SimpleNamespace(prompt_token_count=200, candidates_token_count=80)
        )
        _after_model(ctx, resp)  # type: ignore[arg-type]

        assert ctx.state[_STATE_TOKENS_IN] == 200
        assert ctx.state[_STATE_TOKENS_OUT] == 80

    def test_accumulates_across_multiple_calls(self):
        ctx = _make_callback_context(**{_STATE_TOKENS_IN: 100, _STATE_TOKENS_OUT: 50})
        resp = SimpleNamespace(
            usage_metadata=SimpleNamespace(prompt_token_count=300, candidates_token_count=70)
        )
        _after_model(ctx, resp)  # type: ignore[arg-type]

        assert ctx.state[_STATE_TOKENS_IN] == 400
        assert ctx.state[_STATE_TOKENS_OUT] == 120

    def test_degrades_gracefully_when_usage_metadata_missing(self):
        ctx = _make_callback_context()
        resp = SimpleNamespace()  # no usage_metadata attribute
        _after_model(ctx, resp)  # type: ignore[arg-type]

        assert ctx.state[_STATE_TOKENS_IN] == 0
        assert ctx.state[_STATE_TOKENS_OUT] == 0

    def test_handles_none_token_counts(self):
        ctx = _make_callback_context()
        resp = SimpleNamespace(
            usage_metadata=SimpleNamespace(prompt_token_count=None, candidates_token_count=None)
        )
        _after_model(ctx, resp)  # type: ignore[arg-type]

        assert ctx.state[_STATE_TOKENS_IN] == 0
        assert ctx.state[_STATE_TOKENS_OUT] == 0


# ---------------------------------------------------------------------------
# _clear_history
# ---------------------------------------------------------------------------


class TestClearHistory:
    def test_clears_contents(self):
        ctx = _make_callback_context()
        request = SimpleNamespace(contents=["message-1", "message-2"])
        _clear_history(ctx, request)  # type: ignore[arg-type]

        assert request.contents == []

    def test_handles_none_request(self):
        ctx = _make_callback_context()
        # Should not raise when request is None
        _clear_history(ctx, None)  # type: ignore[arg-type]

    def test_handles_empty_contents(self):
        ctx = _make_callback_context()
        request = SimpleNamespace(contents=[])
        _clear_history(ctx, request)  # type: ignore[arg-type]

        assert request.contents == []


# ---------------------------------------------------------------------------
# _apply_priority_weights
# ---------------------------------------------------------------------------


def _make_impact_json(**overrides) -> str:
    """Build a minimal ImpactResult-shaped JSON string for testing."""
    base = {
        "event_id": "EXC-001",
        "affected_shipments": [],
        "total_value_at_risk_inr": 0,
        "total_penalty_exposure_inr": 0,
        "hub_congestion_risk": "LOW",
        "recommended_priority_order": [],
    }
    base.update(overrides)
    return json.dumps(base)


def _make_shipment(shipment_id: str, **overrides) -> dict:
    """Build a minimal shipment dict for weight testing."""
    base = {
        "shipment_id": shipment_id,
        "value_inr": 100_000,
        "penalty_amount_inr": 5_000,
        "churn_risk": "MEDIUM",
        "customer_tier": "",
        "public_facing_deadline": False,
        "hours_until_deadline": None,
        "remaining_route_legs": None,
        "current_route_leg": None,
    }
    base.update(overrides)
    return base


class TestApplyPriorityWeights:
    def test_basic_priority_scoring_orders_by_score(self):
        high_value_shipment = _make_shipment(
            "ship-high",
            value_inr=1_000_000,
            penalty_amount_inr=20_000,
            churn_risk="HIGH",
        )
        low_value_shipment = _make_shipment(
            "ship-low",
            value_inr=10_000,
            penalty_amount_inr=500,
            churn_risk="LOW",
        )

        raw_json = _make_impact_json(affected_shipments=[high_value_shipment, low_value_shipment])
        ctx = _make_callback_context(**{"triage:impact": raw_json})

        _apply_priority_weights(ctx, raw_json)

        assert "triage:impact" in ctx.state
        assert "triage:impact_weights" in ctx.state
        result = json.loads(ctx.state["triage:impact"])
        priority_order = result["recommended_priority_order"]
        assert priority_order[0] == "ship-high"
        assert priority_order[1] == "ship-low"

    def test_public_facing_deadline_boost_applied(self):
        with_deadline = _make_shipment(
            "ship-deadline",
            value_inr=100_000,
            public_facing_deadline=True,
        )
        without_deadline = _make_shipment(
            "ship-no-deadline",
            value_inr=100_000,
            public_facing_deadline=False,
        )

        raw_json = _make_impact_json(affected_shipments=[without_deadline, with_deadline])
        ctx = _make_callback_context(**{"triage:impact": raw_json})

        _apply_priority_weights(ctx, raw_json)

        weights = json.loads(ctx.state["triage:impact_weights"])
        assert weights["ship-deadline"]["final_score"] > weights["ship-no-deadline"]["final_score"]
        assert "public_facing_deadline" in weights["ship-deadline"]["hard_overrides_applied"]

    def test_urgent_deadline_boost_stacks(self):
        # hours_until_deadline=5 → < 24h (+0.2) AND < 6h (+0.4), stacking
        critical_deadline = _make_shipment("ship-critical", hours_until_deadline=5)
        # hours_until_deadline=15 → only < 24h (+0.2)
        urgent_deadline = _make_shipment("ship-urgent", hours_until_deadline=15)
        # No deadline
        no_deadline = _make_shipment("ship-no-deadline")

        raw_json = _make_impact_json(
            affected_shipments=[no_deadline, urgent_deadline, critical_deadline]
        )
        ctx = _make_callback_context(**{"triage:impact": raw_json})

        _apply_priority_weights(ctx, raw_json)

        weights = json.loads(ctx.state["triage:impact_weights"])
        score_critical = weights["ship-critical"]["final_score"]
        score_urgent = weights["ship-urgent"]["final_score"]
        score_none = weights["ship-no-deadline"]["final_score"]

        # critical (5h) gets more than urgent (15h) gets more than none
        assert score_critical > score_urgent > score_none

        # Check that labels reflect both bumps for the critical shipment
        labels_critical = weights["ship-critical"]["hard_overrides_applied"]
        assert "hours_until_deadline_lt_6" in labels_critical

        labels_urgent = weights["ship-urgent"]["hard_overrides_applied"]
        assert "hours_until_deadline_lt_24" in labels_urgent

    def test_churn_tier_bonus_for_new_customer(self):
        new_customer_ship = _make_shipment(
            "ship-new-cust",
            value_inr=100_000,
            churn_risk="LOW",
            customer_tier="new",  # +0.2 tier bonus on top of LOW=0.2 base
        )
        standard_ship = _make_shipment(
            "ship-standard",
            value_inr=100_000,
            churn_risk="LOW",
            customer_tier="",  # no tier bonus
        )

        raw_json = _make_impact_json(affected_shipments=[standard_ship, new_customer_ship])
        ctx = _make_callback_context(**{"triage:impact": raw_json})

        _apply_priority_weights(ctx, raw_json)

        weights = json.loads(ctx.state["triage:impact_weights"])
        assert weights["ship-new-cust"]["churn"] > weights["ship-standard"]["churn"]
        # new customer churn score = min(0.2 + 0.2, 1.0) = 0.4
        assert abs(weights["ship-new-cust"]["churn"] - 0.4) < 0.001
        # standard churn score = 0.2 + 0.0 = 0.2
        assert abs(weights["ship-standard"]["churn"] - 0.2) < 0.001

    def test_graceful_failure_on_invalid_json(self):
        ctx = _make_callback_context()
        # Should not raise — invalid JSON is swallowed silently
        _apply_priority_weights(ctx, "not valid json at all {{{")
        # State should not have been written
        assert "triage:impact_weights" not in ctx.state

    def test_graceful_failure_on_empty_shipments(self):
        raw_json = _make_impact_json(affected_shipments=[])
        ctx = _make_callback_context(**{"triage:impact": raw_json})

        # Should not raise and should not write weights
        _apply_priority_weights(ctx, raw_json)

        assert "triage:impact_weights" not in ctx.state

    def test_score_clamped_at_max(self):
        # A shipment with all boosts applied should not exceed _SCORE_MAX=2.0
        ship = _make_shipment(
            "ship-all-boosts",
            value_inr=1_000_000,
            penalty_amount_inr=999_999,
            churn_risk="HIGH",
            customer_tier="new",
            public_facing_deadline=True,
            hours_until_deadline=2,  # < 6h → +0.4, also < 24h → +0.2
        )

        raw_json = _make_impact_json(
            affected_shipments=[ship],
            hub_congestion_risk="CRITICAL",
        )
        ctx = _make_callback_context(**{"triage:impact": raw_json})

        _apply_priority_weights(ctx, raw_json)

        weights = json.loads(ctx.state["triage:impact_weights"])
        assert weights["ship-all-boosts"]["final_score"] <= 2.0

    def test_recommended_priority_order_written_to_impact_state(self):
        ships = [
            _make_shipment("ship-a", value_inr=50_000),
            _make_shipment("ship-b", value_inr=200_000),
        ]
        raw_json = _make_impact_json(affected_shipments=ships)
        ctx = _make_callback_context(**{"triage:impact": raw_json})

        _apply_priority_weights(ctx, raw_json)

        result = json.loads(ctx.state["triage:impact"])
        assert "recommended_priority_order" in result
        assert set(result["recommended_priority_order"]) == {"ship-a", "ship-b"}

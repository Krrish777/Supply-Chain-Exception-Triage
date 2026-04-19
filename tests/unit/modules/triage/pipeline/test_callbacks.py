"""Unit tests for pipeline callbacks — U-1 through U-10.

Tests are grouped by rule:
    U-1 .. U-7  — _rule_b_safety_check  (Rule B)
    U-8         — _rule_cf_skip_check   (Rule B sentinel)
    U-9         — _rule_cf_skip_check   (Rule C)
    U-10        — _rule_cf_skip_check   (Rule F)
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock

os.environ.setdefault("GCP_PROJECT_ID", "sct-test")
os.environ.setdefault("FIREBASE_PROJECT_ID", "sct-test")
os.environ.setdefault("SCT_DISABLE_SECRET_MANAGER", "1")

from supply_chain_triage.modules.triage.pipeline.callbacks import (
    _rule_b_safety_check,
    _rule_cf_skip_check,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _ctx(state: dict | None = None) -> MagicMock:
    """Build a minimal CallbackContext mock with a real dict as state."""
    ctx = MagicMock()
    ctx.state = state or {}
    return ctx


def _classification_json(
    exception_type: str = "carrier_capacity_failure", severity: str = "HIGH"
) -> str:
    return json.dumps(
        {
            "exception_type": exception_type,
            "subtype": "test",
            "severity": severity,
            "confidence": 0.9,
            "key_facts": [],
            "reasoning": "test",
            "requires_human_approval": False,
            "safety_escalation": None,
        }
    )


# ---------------------------------------------------------------------------
# U-1 … U-7 — Rule B
# ---------------------------------------------------------------------------


class TestRuleBSafetyCheck:
    # U-1
    def test_no_event_text_proceeds(self):
        ctx = _ctx()
        result = _rule_b_safety_check(ctx)
        assert result is None
        assert "triage:status" not in ctx.state

    # U-2
    def test_empty_string_proceeds(self):
        ctx = _ctx({"triage:event_raw_text": ""})
        result = _rule_b_safety_check(ctx)
        assert result is None

    # U-3
    def test_english_keyword_returns_content(self):
        ctx = _ctx({"triage:event_raw_text": "There was a fire at the warehouse."})
        result = _rule_b_safety_check(ctx)
        assert result is not None
        assert result.role == "model"
        assert result.parts
        assert ctx.state["triage:status"] == "escalated_to_human_safety"
        assert ctx.state["triage:skip_impact"] is True
        assert ctx.state["triage:rule_b_applied"] is True
        assert ctx.state["triage:escalation_priority"] == "safety"

    # U-4
    def test_hindi_keyword_returns_content(self):
        ctx = _ctx({"triage:event_raw_text": "Driver ne kaha situation khatarnak hai."})
        result = _rule_b_safety_check(ctx)
        assert result is not None
        assert "khatarnak" in ctx.state["triage:safety_match"]

    # U-5
    def test_nfkc_normalization_catches_fullwidth(self):
        # Full-width "ｆｉｒｅ" normalises to "fire" after NFKC + casefold
        ctx = _ctx({"triage:event_raw_text": "ｆｉｒｅ at depot"})
        result = _rule_b_safety_check(ctx)
        assert result is not None
        assert "fire" in ctx.state["triage:safety_match"]

    # U-6
    def test_safety_match_list_populated(self):
        ctx = _ctx({"triage:event_raw_text": "accident and injury reported on route"})
        _rule_b_safety_check(ctx)
        matched = ctx.state["triage:safety_match"]
        assert isinstance(matched, list)
        assert "accident" in matched
        assert "injury" in matched

    # U-7
    def test_placeholder_classification_written(self):
        ctx = _ctx({"triage:event_raw_text": "tanker explosion on NH-48"})
        _rule_b_safety_check(ctx)
        raw = ctx.state.get("triage:classification")
        assert raw is not None
        data = json.loads(raw)
        assert data["exception_type"] == "safety_incident"
        assert data["severity"] == "CRITICAL"
        assert data["requires_human_approval"] is True
        assert data["safety_escalation"]["trigger_type"] == "keyword_detection"
        assert "tanker explosion" in data["safety_escalation"]["matched_terms"]


# ---------------------------------------------------------------------------
# U-8 … U-10 — Rule C/F
# ---------------------------------------------------------------------------


class TestRuleCFSkipCheck:
    # U-8
    def test_rule_b_sentinel_skips_impact(self):
        ctx = _ctx({"triage:skip_impact": True})
        result = _rule_cf_skip_check(ctx)
        assert result is not None
        assert result.role == "model"

    # U-9
    def test_regulatory_forces_impact(self):
        ctx = _ctx(
            {
                "triage:classification": _classification_json(
                    exception_type="regulatory_compliance", severity="LOW"
                )
            }
        )
        result = _rule_cf_skip_check(ctx)
        assert result is None
        assert ctx.state.get("triage:rule_c_applied") is True

    # U-10
    def test_low_severity_skips_impact(self):
        ctx = _ctx({"triage:classification": _classification_json(severity="LOW")})
        result = _rule_cf_skip_check(ctx)
        assert result is not None
        assert ctx.state["triage:skip_impact"] is True
        assert ctx.state["triage:status"] == "complete"
        assert ctx.state.get("triage:rule_f_applied") is True

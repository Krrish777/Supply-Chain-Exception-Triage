"""Tests for TriageResult schema (test-plan §1.7, §1.8)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from supply_chain_triage.modules.triage.models.triage_result import TriageResult


class TestTriageResultStatusEnum:
    def test_rejects_invalid_status(self) -> None:
        # Given: status="totally_fine" not in the TriageStatus literal
        payload = {
            "event_id": "ev_001",
            "status": "totally_fine",
            "coordinator_trace": [],
            "classification": None,
            "impact": None,
            "summary": "",
            "processing_time_ms": 0,
            "errors": [],
            "escalation_priority": None,
        }
        # When / Then: ValidationError on status
        with pytest.raises(ValidationError) as excinfo:
            TriageResult.model_validate(payload)
        assert "status" in str(excinfo.value)


class TestTriageResultAllowsImpactNone:
    def test_rule_f_skip_impact_is_none(self) -> None:
        # Given: TriageResult with impact=None (Rule F skip) and status=complete
        payload = {
            "event_id": "ev_001",
            "status": "complete",
            "coordinator_trace": [],
            "classification": None,
            "impact": None,  # Rule F skipped the Impact Agent
            "summary": "Low-severity customer escalation; no impact run.",
            "processing_time_ms": 1200,
            "errors": [],
            "escalation_priority": None,
        }
        # When: parsed
        result = TriageResult.model_validate(payload)
        # Then: succeeds with impact=None
        assert result.impact is None
        assert result.status == "complete"

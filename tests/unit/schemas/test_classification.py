"""Tests for ClassificationResult schema (test-plan §1.3, §1.4)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from supply_chain_triage.modules.triage.models.classification import (
    ClassificationResult,
    ExceptionType,
    Severity,
)


def _base_result(**overrides: object) -> dict[str, object]:
    """Build a minimal valid ClassificationResult dict; overrides merge in."""
    base = {
        "exception_type": ExceptionType.carrier_capacity_failure.value,
        "subtype": "vehicle_breakdown_in_transit",
        "severity": Severity.HIGH.value,
        "urgency_hours": 4,
        "confidence": 0.85,
        "key_facts": [{"key": "vehicle_id", "value": "MH-12-AB-1234"}],
        "reasoning": "Driver reported breakdown; 4h repair window given NH-48 traffic.",
        "requires_human_approval": False,
        "tools_used": ["check_safety_keywords", "translate_text"],
        "safety_escalation": None,
    }
    base.update(overrides)
    return base


class TestConfidenceValidation:
    def test_round_trips_confidence_0_to_1(self) -> None:
        # Given: ClassificationResult with confidence=0.85
        parsed = ClassificationResult.model_validate(_base_result(confidence=0.85))
        # When: serialized and reparsed
        reparsed = ClassificationResult.model_validate(parsed.model_dump(mode="json"))
        # Then: confidence preserved exactly
        assert reparsed.confidence == 0.85

    def test_rejects_confidence_above_one(self) -> None:
        # Given: confidence=1.5
        # When / Then: ValidationError on confidence
        with pytest.raises(ValidationError) as excinfo:
            ClassificationResult.model_validate(_base_result(confidence=1.5))
        assert "confidence" in str(excinfo.value)

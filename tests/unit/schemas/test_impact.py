"""Tests for ImpactResult + ShipmentImpact schemas (test-plan §1.5, §1.6)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from supply_chain_triage.modules.triage.models.impact import ImpactResult, ShipmentImpact


def _shipment(**overrides: object) -> dict[str, object]:
    base = {
        "shipment_id": "sh_001",
        "customer_id": "cu_001",
        "customer_name": "Trina Logistics",
        "customer_tier": "high_value",
        "customer_type": "b2b",
        "product_description": "Industrial bearings",
        "value_inr": 125_000,
        "destination": "Pune",
        "deadline": "2026-04-15T09:00:00+00:00",
        "hours_until_deadline": 21.0,
        "sla_breach_risk": "HIGH",
        "churn_risk": "MEDIUM",
        "penalty_amount_inr": 5_000,
        "public_facing_deadline": False,
        "reputation_risk_note": None,
        "reputation_risk_source": None,
        "special_notes": None,
    }
    base.update(overrides)
    return base


class TestImpactResultEmptyAffectedShipments:
    def test_empty_shipments_list_is_valid(self) -> None:
        # Given: ImpactResult with empty affected_shipments, zero totals
        payload = {
            "event_id": "ev_001",
            "affected_shipments": [],
            "total_value_at_risk_inr": 0,
            "total_penalty_exposure_inr": 0,
            "estimated_churn_impact_inr": 0,
            "critical_path_shipment_id": None,
            "recommended_priority_order": [],
            "priority_reasoning": "",
            "has_reputation_risks": False,
            "reputation_risk_shipments": [],
            "summary": "No shipments affected.",
        }
        # When: parsed
        result = ImpactResult.model_validate(payload)
        # Then: no error AND has_reputation_risks is False
        assert result.affected_shipments == []
        assert result.has_reputation_risks is False


class TestShipmentImpactRequiresDeadline:
    def test_missing_deadline_raises(self) -> None:
        # Given: ShipmentImpact dict without deadline
        payload = _shipment()
        del payload["deadline"]
        # When / Then: ValidationError naming deadline
        with pytest.raises(ValidationError) as excinfo:
            ShipmentImpact.model_validate(payload)
        assert "deadline" in str(excinfo.value)

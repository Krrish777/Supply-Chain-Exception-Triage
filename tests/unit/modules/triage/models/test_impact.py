"""Tests for ImpactResult + ShipmentImpact models (Sprint 2 schema)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from supply_chain_triage.modules.triage.models.impact import ImpactResult, ShipmentImpact


def _shipment(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
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


def _impact_result(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "event_id": "ev_001",
        "affected_shipments": [],
        "total_value_at_risk_inr": 0,
        "total_penalty_exposure_inr": 0,
    }
    base.update(overrides)
    return base


class TestShipmentImpactConstruction:
    def test_minimal_required_fields_construct(self) -> None:
        shipment = ShipmentImpact.model_validate(_shipment())
        assert shipment.shipment_id == "sh_001"
        assert shipment.customer_tier == "high_value"

    def test_missing_deadline_raises(self) -> None:
        payload = _shipment()
        del payload["deadline"]
        with pytest.raises(ValidationError) as excinfo:
            ShipmentImpact.model_validate(payload)
        assert "deadline" in str(excinfo.value)

    def test_no_extra_forbid_allows_extra_keys(self) -> None:
        # extra="forbid" removed — extra keys must not raise
        payload = _shipment(unknown_field_from_gemini="some_value")
        shipment = ShipmentImpact.model_validate(payload)
        assert shipment.shipment_id == "sh_001"


class TestShipmentImpactFinancialFields:
    def test_financial_fields_default_to_zero(self) -> None:
        shipment = ShipmentImpact.model_validate(_shipment())
        assert shipment.rerouting_cost_inr == 0
        assert shipment.holding_cost_inr == 0
        assert shipment.opportunity_cost_inr == 0

    def test_financial_fields_accept_positive_values(self) -> None:
        shipment = ShipmentImpact.model_validate(
            _shipment(
                rerouting_cost_inr=8_000,
                holding_cost_inr=3_500,
                opportunity_cost_inr=1_200,
            )
        )
        assert shipment.rerouting_cost_inr == 8_000
        assert shipment.holding_cost_inr == 3_500
        assert shipment.opportunity_cost_inr == 1_200

    def test_financial_fields_reject_negative_values(self) -> None:
        with pytest.raises(ValidationError):
            ShipmentImpact.model_validate(_shipment(rerouting_cost_inr=-1))

    def test_route_leg_fields_default_to_none(self) -> None:
        shipment = ShipmentImpact.model_validate(_shipment())
        assert shipment.current_route_leg is None
        assert shipment.remaining_route_legs is None

    def test_route_leg_fields_accept_integers(self) -> None:
        shipment = ShipmentImpact.model_validate(
            _shipment(current_route_leg=2, remaining_route_legs=5)
        )
        assert shipment.current_route_leg == 2
        assert shipment.remaining_route_legs == 5


class TestImpactResultConstruction:
    def test_minimal_required_fields_construct(self) -> None:
        result = ImpactResult.model_validate(_impact_result())
        assert result.event_id == "ev_001"
        assert result.affected_shipments == []

    def test_no_extra_forbid_allows_extra_keys(self) -> None:
        # extra="forbid" removed — extra keys must not raise
        payload = _impact_result(unknown_field_from_gemini="extra")
        result = ImpactResult.model_validate(payload)
        assert result.event_id == "ev_001"

    def test_impact_weights_used_field_absent(self) -> None:
        # dict[str, Any] field removed to satisfy Gemini additionalProperties constraint
        result = ImpactResult.model_validate(_impact_result())
        assert not hasattr(result, "impact_weights_used")


class TestImpactResultRippleFields:
    def test_ripple_fields_default_values(self) -> None:
        result = ImpactResult.model_validate(_impact_result())
        assert result.total_financial_exposure_inr == 0
        assert result.cascade_risk_summary == ""
        assert result.hub_congestion_risk is None
        assert result.estimated_delay_hours == 0.0

    def test_ripple_fields_accept_values(self) -> None:
        result = ImpactResult.model_validate(
            _impact_result(
                total_financial_exposure_inr=500_000,
                cascade_risk_summary="Delay at Mumbai hub cascades to 3 downstream shipments.",
                hub_congestion_risk="HIGH",
                estimated_delay_hours=18.5,
            )
        )
        assert result.total_financial_exposure_inr == 500_000
        assert "Mumbai" in result.cascade_risk_summary
        assert result.hub_congestion_risk == "HIGH"
        assert result.estimated_delay_hours == 18.5

    def test_total_financial_exposure_rejects_negative(self) -> None:
        with pytest.raises(ValidationError):
            ImpactResult.model_validate(_impact_result(total_financial_exposure_inr=-1))


class TestImpactResultExistingFields:
    def test_has_reputation_risks_defaults_false(self) -> None:
        result = ImpactResult.model_validate(_impact_result())
        assert result.has_reputation_risks is False

    def test_recommended_priority_order_defaults_empty(self) -> None:
        result = ImpactResult.model_validate(_impact_result())
        assert result.recommended_priority_order == []

    def test_affected_shipments_roundtrip(self) -> None:
        shipment_data = _shipment()
        result = ImpactResult.model_validate(
            _impact_result(
                affected_shipments=[shipment_data],
                total_value_at_risk_inr=125_000,
                total_penalty_exposure_inr=5_000,
            )
        )
        assert len(result.affected_shipments) == 1
        assert result.affected_shipments[0].shipment_id == "sh_001"
        assert result.total_value_at_risk_inr == 125_000

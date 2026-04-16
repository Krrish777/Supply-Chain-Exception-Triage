"""Tests for FinancialBreakdown model used by the Impact Agent."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from supply_chain_triage.modules.triage.models.financial import FinancialBreakdown


def _valid_breakdown(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "shipment_value_inr": 500_000,
        "total_exposure_inr": 550_000,
    }
    base.update(overrides)
    return base


class TestFinancialBreakdown:
    def test_valid_construction_minimal(self) -> None:
        fb = FinancialBreakdown(**_valid_breakdown())
        assert fb.shipment_value_inr == 500_000
        assert fb.total_exposure_inr == 550_000
        # Optional cost fields default to 0
        assert fb.penalty_amount_inr == 0
        assert fb.rerouting_cost_inr == 0
        assert fb.holding_cost_inr == 0
        assert fb.opportunity_cost_inr == 0

    def test_breakdown_notes_defaults_to_empty_string(self) -> None:
        fb = FinancialBreakdown(**_valid_breakdown())
        assert fb.breakdown_notes == ""

    def test_valid_construction_all_fields(self) -> None:
        fb = FinancialBreakdown(
            shipment_value_inr=1_000_000,
            penalty_amount_inr=50_000,
            rerouting_cost_inr=20_000,
            holding_cost_inr=10_000,
            opportunity_cost_inr=15_000,
            total_exposure_inr=1_095_000,
            breakdown_notes="SLA breach penalty applied; NH-48 diversion costs added.",
        )
        assert fb.penalty_amount_inr == 50_000
        assert fb.breakdown_notes == "SLA breach penalty applied; NH-48 diversion costs added."

    def test_rejects_negative_shipment_value(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            FinancialBreakdown(**_valid_breakdown(shipment_value_inr=-1))
        assert "shipment_value_inr" in str(excinfo.value)

    def test_rejects_negative_penalty(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            FinancialBreakdown(**_valid_breakdown(penalty_amount_inr=-100))
        assert "penalty_amount_inr" in str(excinfo.value)

    def test_rejects_negative_rerouting_cost(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            FinancialBreakdown(**_valid_breakdown(rerouting_cost_inr=-1))
        assert "rerouting_cost_inr" in str(excinfo.value)

    def test_rejects_negative_holding_cost(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            FinancialBreakdown(**_valid_breakdown(holding_cost_inr=-1))
        assert "holding_cost_inr" in str(excinfo.value)

    def test_rejects_negative_opportunity_cost(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            FinancialBreakdown(**_valid_breakdown(opportunity_cost_inr=-1))
        assert "opportunity_cost_inr" in str(excinfo.value)

    def test_rejects_negative_total_exposure(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            FinancialBreakdown(**_valid_breakdown(total_exposure_inr=-1))
        assert "total_exposure_inr" in str(excinfo.value)

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            FinancialBreakdown(**_valid_breakdown(unexpected_key="boom"))

    def test_zero_values_accepted(self) -> None:
        # Shipment value of 0 is valid (e.g. samples, promotional goods)
        fb = FinancialBreakdown(shipment_value_inr=0, total_exposure_inr=0)
        assert fb.shipment_value_inr == 0
        assert fb.total_exposure_inr == 0

    def test_model_round_trips(self) -> None:
        fb = FinancialBreakdown(
            shipment_value_inr=200_000,
            penalty_amount_inr=5_000,
            total_exposure_inr=205_000,
            breakdown_notes="Minor penalty applied.",
        )
        reparsed = FinancialBreakdown.model_validate(fb.model_dump(mode="json"))
        assert reparsed == fb

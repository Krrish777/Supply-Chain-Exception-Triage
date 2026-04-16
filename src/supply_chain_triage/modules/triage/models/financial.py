"""Financial breakdown models for Impact Agent cost calculations.

Internal model — NOT used as output_schema. Used by the
``calculate_financial_impact`` tool to return deterministic cost breakdowns.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FinancialBreakdown(BaseModel):
    """Deterministic financial impact breakdown for a single shipment."""

    model_config = ConfigDict(extra="forbid")

    shipment_value_inr: int = Field(..., ge=0)
    penalty_amount_inr: int = Field(0, ge=0)
    rerouting_cost_inr: int = Field(0, ge=0)
    holding_cost_inr: int = Field(0, ge=0)
    opportunity_cost_inr: int = Field(0, ge=0)
    total_exposure_inr: int = Field(..., ge=0)
    breakdown_notes: str = ""

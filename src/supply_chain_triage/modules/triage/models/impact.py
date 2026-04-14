"""ImpactResult + ShipmentImpact — output of the Impact Agent.

Rule E (reputation risk) fields sourced from
``docs/research/Supply-Chain-Agent-Spec-Impact.md`` §234-243. Dynamic impact
weighting rules documented in the same note at §198-221.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 — runtime-needed by Pydantic validation
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ShipmentImpact(BaseModel):
    """Impact assessment for a single affected shipment."""

    model_config = ConfigDict(extra="forbid")

    shipment_id: str = Field(..., min_length=1)
    customer_id: str = Field(..., min_length=1)
    customer_name: str
    customer_tier: Literal["high_value", "repeat_standard", "new", "b2b_enterprise"]
    customer_type: Literal["d2c", "b2b", "marketplace"]

    product_description: str
    value_inr: int = Field(..., ge=0)
    destination: str

    # CR3 + `models.md` §2: tz-aware datetime, not string. Pydantic parses
    # ISO-8601 input and round-trips via model_dump(mode="json"). Firestore
    # returns tz-aware timestamps on read — str here would break serialization.
    deadline: datetime = Field(..., description="Deadline (tz-aware)")
    hours_until_deadline: float

    sla_breach_risk: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    churn_risk: Literal["LOW", "MEDIUM", "HIGH"]
    penalty_amount_inr: int | None = Field(None, ge=0)

    # Rule E: Reputation risk flag
    public_facing_deadline: bool = False
    reputation_risk_note: str | None = None
    reputation_risk_source: Literal["metadata_flag", "llm_inference"] | None = None

    special_notes: str | None = None


class ImpactResult(BaseModel):
    """Aggregate impact result returned by the Impact Agent."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    affected_shipments: list[ShipmentImpact] = Field(default_factory=list)

    total_value_at_risk_inr: int = Field(..., ge=0)
    total_penalty_exposure_inr: int = Field(..., ge=0)
    estimated_churn_impact_inr: int | None = Field(None, ge=0)

    critical_path_shipment_id: str | None = None
    recommended_priority_order: list[str] = Field(default_factory=list)
    priority_reasoning: str = ""

    impact_weights_used: dict[str, Any] = Field(
        default_factory=dict,
        description="Weights LLM chose per-exception for (value, penalty, churn) + reasoning",
    )

    has_reputation_risks: bool = False
    reputation_risk_shipments: list[str] = Field(default_factory=list)

    tools_used: list[str] = Field(default_factory=list)
    summary: str = ""

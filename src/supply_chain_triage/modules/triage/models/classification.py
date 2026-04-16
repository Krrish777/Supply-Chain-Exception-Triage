"""ClassificationResult — output of the Classifier Agent.

Taxonomy + severity enums sourced from
``docs/research/Supply-Chain-Agent-Spec-Classifier.md`` §28-63.

Note: ``dict[str, Any]`` is not supported by Gemini's ``output_schema``
(``additionalProperties`` rejected by the SDK). Key facts and safety
escalation use flat Pydantic models instead. See googleapis/python-genai#1113.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from supply_chain_triage.modules.triage.models.common_types import Severity  # noqa: TC001
from supply_chain_triage.modules.triage.models.shared_models import (  # noqa: TC001
    KeyFact,
    SafetyEscalation,
)


class ExceptionType(StrEnum):
    """6 exception categories per Classifier spec §28-63."""

    carrier_capacity_failure = "carrier_capacity_failure"
    route_disruption = "route_disruption"
    regulatory_compliance = "regulatory_compliance"
    customer_escalation = "customer_escalation"
    external_disruption = "external_disruption"
    safety_incident = "safety_incident"


class ClassificationResult(BaseModel):
    """Structured classification from the Classifier Agent."""

    # NOTE: no extra="forbid" — Gemini API rejects additionalProperties in schema.
    # Validation at API boundaries uses a separate model with extra="forbid".
    model_config = ConfigDict(use_enum_values=True)

    exception_type: ExceptionType
    subtype: str = Field(..., min_length=1)
    severity: Severity
    urgency_hours: int | None = Field(
        None, ge=0, description="Estimated hours until situation becomes critical"
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    key_facts: list[KeyFact] = Field(
        default_factory=list, description="Structured facts extracted from raw content"
    )
    reasoning: str = Field(..., min_length=1, max_length=2000)
    requires_human_approval: bool = False
    tools_used: list[str] = Field(default_factory=list)
    safety_escalation: SafetyEscalation | None = None

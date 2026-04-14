"""ClassificationResult — output of the Classifier Agent.

Taxonomy + severity enums sourced from
``docs/research/Supply-Chain-Agent-Spec-Classifier.md`` §28-63.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExceptionType(StrEnum):
    """6 exception categories per Classifier spec §28-63."""

    carrier_capacity_failure = "carrier_capacity_failure"
    route_disruption = "route_disruption"
    regulatory_compliance = "regulatory_compliance"
    customer_escalation = "customer_escalation"
    external_disruption = "external_disruption"
    safety_incident = "safety_incident"


class Severity(StrEnum):
    """4 severity levels. Classifier's severity validator can only escalate, never downgrade."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ClassificationResult(BaseModel):
    """Structured classification from the Classifier Agent."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    exception_type: ExceptionType
    subtype: str = Field(..., min_length=1)
    severity: Severity
    urgency_hours: int | None = Field(
        None, ge=0, description="Estimated hours until situation becomes critical"
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    key_facts: dict[str, Any] = Field(
        ..., description="Structured facts extracted from raw content"
    )
    reasoning: str = Field(..., min_length=1, max_length=2000)
    requires_human_approval: bool = False
    tools_used: list[str] = Field(default_factory=list)
    safety_escalation: dict[str, Any] | None = None

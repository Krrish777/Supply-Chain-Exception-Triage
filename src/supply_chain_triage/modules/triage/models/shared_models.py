"""Reusable sub-models shared across triage outputs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class KeyFact(BaseModel):
    """Single extracted fact from exception content."""

    model_config = ConfigDict()

    key: str = Field(..., description="Fact name (e.g. carrier_name, location)")
    value: str = Field(..., description="Extracted value")


class SafetyEscalation(BaseModel):
    """Safety escalation details when safety keywords are detected."""

    model_config = ConfigDict()

    trigger_type: str = Field(..., description="keyword_detection or classification")
    matched_terms: list[str] = Field(default_factory=list, description="Safety keywords found")
    escalation_reason: str = Field(..., description="Why this was escalated")

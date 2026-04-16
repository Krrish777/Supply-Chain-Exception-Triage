"""Thin request envelopes shared by triage agent test endpoints."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TriageAgentInput(BaseModel):
    """Input envelope for the classifier and impact test endpoints."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., min_length=1, description="Firestore exception event ID")

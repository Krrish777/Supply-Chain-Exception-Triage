"""Thin request envelopes shared by triage agent test endpoints."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TriageAgentInput(BaseModel):
    """Input envelope for the classifier and impact test endpoints."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., min_length=1, description="Firestore exception event ID")


class TriagePayload(BaseModel):
    """Input envelope for POST /api/v1/triage — accepts event_id OR raw_text."""

    model_config = ConfigDict(extra="forbid")

    event_id: str | None = Field(default=None, max_length=64)
    raw_text: str | None = Field(default=None, max_length=8000)

    @model_validator(mode="after")
    def _at_least_one_non_empty(self) -> TriagePayload:
        # Whitespace-only counts as empty — the pipeline has nothing to scan.
        if not (self.event_id or "").strip() and not (self.raw_text or "").strip():
            msg = "one of event_id / raw_text must be non-empty"
            raise ValueError(msg)
        return self

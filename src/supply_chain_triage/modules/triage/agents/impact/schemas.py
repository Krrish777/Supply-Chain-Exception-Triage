"""Impact agent input schema -- thin envelope for the test endpoint."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ImpactInput(BaseModel):
    """Input payload for the Impact agent test runner."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., min_length=1, description="Exception event ID to assess impact for")

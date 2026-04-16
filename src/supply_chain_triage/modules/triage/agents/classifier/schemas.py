"""Classifier agent I/O schemas.

``ClassifierInput`` is the thin envelope sent by the test endpoint.
``ClassificationResult`` lives in ``modules/triage/models/classification.py``
(shared across agents) and is reused here as the formatter's ``output_schema``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ClassifierInput(BaseModel):
    """Input envelope for the classifier test endpoint."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., min_length=1, description="Firestore exception event ID")

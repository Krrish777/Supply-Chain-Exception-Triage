"""ExceptionEvent — raw input to the triage pipeline.

Source of truth: ``docs/research/Supply-Chain-Agent-Spec-Coordinator.md``.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 — runtime-needed by Pydantic validation
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SourceChannel = Literal[
    "whatsapp_voice",
    "whatsapp_text",
    "email",
    "phone_call_transcript",
    "carrier_portal_alert",
    "customer_escalation",
    "manual_entry",
]


class ExceptionEvent(BaseModel):
    """The raw exception event received by the Coordinator."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., min_length=1)
    timestamp: datetime
    source_channel: SourceChannel
    sender: dict[str, Any] = Field(..., description="Sender metadata (name, role, etc.)")
    raw_content: str = Field(..., min_length=1, max_length=50_000)
    original_language: str | None = None
    english_translation: str | None = None
    media_urls: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

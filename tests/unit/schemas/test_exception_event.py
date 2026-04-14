"""Tests for ExceptionEvent schema (test-plan §1.1, §1.2)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from supply_chain_triage.modules.triage.models.exception_event import ExceptionEvent


class TestExceptionEventRoundTrip:
    def test_valid_event_round_trips(self) -> None:
        # Given: a valid ExceptionEvent dict per vault Coordinator schema
        original = {
            "event_id": "ev_001",
            "timestamp": datetime(2026, 4, 14, 12, 0, tzinfo=UTC).isoformat(),
            "source_channel": "whatsapp_voice",
            "sender": {"name": "Ravi", "role": "driver"},
            "raw_content": "गाड़ी खराब हो गई NH-48 पर",
            "original_language": "hi",
            "english_translation": "vehicle broken on NH-48",
            "media_urls": [],
            "metadata": {},
        }
        # When: parsed + serialized
        parsed = ExceptionEvent.model_validate(original)
        dumped = parsed.model_dump(mode="json")
        # Then: round-tripped dict equals original (modulo optional defaults)
        assert dumped["event_id"] == original["event_id"]
        assert dumped["source_channel"] == original["source_channel"]
        assert dumped["raw_content"] == original["raw_content"]
        assert dumped["original_language"] == original["original_language"]


class TestExceptionEventSourceChannelValidation:
    def test_rejects_unknown_source_channel(self) -> None:
        # Given: dict with source_channel not in the Literal enum
        payload = {
            "event_id": "ev_002",
            "timestamp": datetime(2026, 4, 14, tzinfo=UTC).isoformat(),
            "source_channel": "carrier_pigeon",
            "sender": {"name": "X"},
            "raw_content": "...",
        }
        # When / Then: ValidationError naming source_channel
        with pytest.raises(ValidationError) as excinfo:
            ExceptionEvent.model_validate(payload)
        assert "source_channel" in str(excinfo.value)

"""Shared triage enums and literals.

These types are used across multiple triage models and agent state fields,
so they live in a single module for reuse and consistency.
"""

from __future__ import annotations

from enum import StrEnum


class Severity(StrEnum):
    """Severity levels shared across classifier and impact models."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SourceChannel(StrEnum):
    """Channels through which an exception can enter the triage pipeline."""

    whatsapp_voice = "whatsapp_voice"
    whatsapp_text = "whatsapp_text"
    email = "email"
    phone_call_transcript = "phone_call_transcript"
    carrier_portal_alert = "carrier_portal_alert"
    customer_escalation = "customer_escalation"
    manual_entry = "manual_entry"


class TriageStatus(StrEnum):
    """Lifecycle states for the final triage result."""

    complete = "complete"
    partial = "partial"
    escalated_to_human = "escalated_to_human"
    escalated_to_human_safety = "escalated_to_human_safety"


class EscalationPriority(StrEnum):
    """Priority labels used by the coordinator when escalating cases."""

    standard = "standard"
    reputation_risk = "reputation_risk"
    safety = "safety"
    regulatory = "regulatory"

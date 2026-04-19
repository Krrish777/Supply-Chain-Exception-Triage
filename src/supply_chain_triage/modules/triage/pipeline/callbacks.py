"""Pipeline-level ADK callbacks implementing the deterministic rule engine.

Rule B fires on the ``triage_pipeline`` SequentialAgent's ``before_agent_callback``.
Returning ``Content`` from that slot skips the entire pipeline (classifier + impact).

Rule C/F fires on the ``impact`` sub-agent's ``before_agent_callback``.
Priority order: B > C > F.

Attachment (Day 3):
    pipeline = SequentialAgent(
        name="triage_pipeline",
        before_agent_callback=_rule_b_safety_check,
        sub_agents=[classifier, impact(before_agent_callback=_rule_cf_skip_check)],
    )
"""

from __future__ import annotations

import copy
import json
import unicodedata
from typing import TYPE_CHECKING, Any

from google.genai import types as genai_types

from supply_chain_triage.modules.triage.pipeline._constants import (
    _RULE_B_SAFETY_KEYWORDS,
    _SAFETY_PLACEHOLDER_BASE,
)

if TYPE_CHECKING:
    from google.adk.agents.callback_context import CallbackContext

_REGULATORY_EXCEPTION_TYPE = "regulatory_compliance"
_LOW_SEVERITY = "LOW"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _skip_content(message: str) -> genai_types.Content:
    """Return a skip-signal Content with role='model'."""
    return genai_types.Content(
        role="model",
        parts=[genai_types.Part(text=message)],
    )


def _classification_dict(state: Any) -> dict[str, Any] | None:
    """Parse triage:classification from state; return dict or None on failure."""
    raw = state.get("triage:classification")
    if not isinstance(raw, str):
        return None
    try:
        result: dict[str, Any] = json.loads(raw)
        return result
    except (json.JSONDecodeError, TypeError):
        return None


def _classification_regulatory(state: Any) -> bool:
    """Return True if the classification exception_type is regulatory_compliance."""
    data = _classification_dict(state)
    if data is None:
        return False
    return data.get("exception_type") == _REGULATORY_EXCEPTION_TYPE


def _classification_severity(state: Any) -> str | None:
    """Return the severity string from triage:classification, or None."""
    data = _classification_dict(state)
    if data is None:
        return None
    return data.get("severity")


def _write_safety_placeholder(state: Any, matched: list[str]) -> None:
    """Write a minimal valid ClassificationResult to state for Rule B short-circuit.

    Prevents runner assembly KeyError — it always reads triage:classification.
    """
    payload = copy.deepcopy(_SAFETY_PLACEHOLDER_BASE)
    payload["safety_escalation"]["matched_terms"] = matched
    state["triage:classification"] = json.dumps(payload)


# ---------------------------------------------------------------------------
# Rule B — pipeline-level safety gate
# ---------------------------------------------------------------------------


def _rule_b_safety_check(callback_context: CallbackContext) -> genai_types.Content | None:
    """Rule B — scan inbound event text for safety keywords before any LLM call.

    Attached to the ``triage_pipeline`` SequentialAgent's ``before_agent_callback``.
    Returning ``Content`` skips the entire pipeline (classifier + impact both skipped).

    Args:
        callback_context: ADK callback context providing session state.

    Returns:
        ``Content`` on keyword match (pipeline skipped); ``None`` to proceed.
    """
    raw = callback_context.state.get("triage:event_raw_text", "")
    if not isinstance(raw, str) or not raw:
        return None

    normalized = unicodedata.normalize("NFKC", raw).casefold()
    matched = sorted(kw for kw in _RULE_B_SAFETY_KEYWORDS if kw in normalized)
    if not matched:
        return None

    callback_context.state["triage:status"] = "escalated_to_human_safety"
    callback_context.state["triage:skip_impact"] = True
    callback_context.state["triage:safety_match"] = matched
    callback_context.state["triage:escalation_priority"] = "safety"
    callback_context.state["triage:rule_b_applied"] = True
    _write_safety_placeholder(callback_context.state, matched)

    return _skip_content(f"Safety-keyword escalation. Matched: {', '.join(matched)}.")


# ---------------------------------------------------------------------------
# Rule C / F — impact gate
# ---------------------------------------------------------------------------


def _rule_cf_skip_check(callback_context: CallbackContext) -> genai_types.Content | None:
    """Rule C/F — gate whether the Impact sub-agent runs.

    Attached to the ``impact`` sub-agent's ``before_agent_callback``.
    Priority: B sentinel > C (regulatory force-run) > F (LOW skip).

    Args:
        callback_context: ADK callback context providing session state.

    Returns:
        ``Content`` to skip Impact; ``None`` to proceed normally.
    """
    state = callback_context.state

    # Rule B sentinel — upstream pipeline callback already short-circuited.
    # Should not be reached when Rule B fires at pipeline level, but kept as
    # a defensive guard for future re-wiring or test scenarios.
    if state.get("triage:skip_impact"):
        return _skip_content("Impact skipped — Rule B safety escalation upstream.")

    # Rule C — regulatory_compliance always runs Impact regardless of severity.
    if _classification_regulatory(state):
        state["triage:rule_c_applied"] = True
        return None

    # Rule F — LOW severity skips Impact (non-regulatory only).
    if _classification_severity(state) == _LOW_SEVERITY:
        state["triage:skip_impact"] = True
        state["triage:status"] = "complete"
        state["triage:rule_f_applied"] = True
        return _skip_content("LOW severity — Impact assessment skipped per Rule F.")

    return None

"""Classifier agent — two-agent pattern (fetcher + formatter).

The fetcher calls tools to retrieve exception + company context. The formatter
applies ``output_schema=ClassificationResult`` to produce structured output.
Wired as ``SequentialAgent`` per ``.claude/rules/agents.md`` §5.

Uses factory function ``create_classifier()`` per ADK cheatsheet guidance to
avoid "agent already has parent" errors in multi-agent compositions.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from google.adk.agents import LlmAgent, SequentialAgent
from google.genai import types as genai_types

from supply_chain_triage.modules.triage.agents.classifier.tools import (
    get_company_profile,
    get_exception_event,
)
from supply_chain_triage.modules.triage.models.classification import (
    ClassificationResult,
    Severity,
)
from supply_chain_triage.utils.logging import get_logger, log_agent_invocation

if TYPE_CHECKING:
    from google.adk.agents.callback_context import CallbackContext
    from google.adk.models.llm_request import LlmRequest
    from google.adk.models.llm_response import LlmResponse

logger = get_logger(__name__)

_AGENT_NAME = "classifier"
_MODEL = "gemini-2.5-flash"
_PROMPTS_DIR = Path(__file__).parent / "prompts"
_FETCHER_INSTRUCTION = (_PROMPTS_DIR / "system_fetcher.md").read_text(encoding="utf-8")
_FORMATTER_INSTRUCTION = (_PROMPTS_DIR / "system_formatter.md").read_text(encoding="utf-8")

# State keys — temp: prefix ensures no leakage to persisted session state.
_STATE_START = f"temp:{_AGENT_NAME}:start_perf_ns"
_STATE_TOKENS_IN = f"temp:{_AGENT_NAME}:tokens_in"
_STATE_TOKENS_OUT = f"temp:{_AGENT_NAME}:tokens_out"

# Severity ordering for escalation-only clamp.
_SEVERITY_ORDER: dict[str, int] = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

# Safety keywords — deterministic detection in _post_classify callback.
_SAFETY_KEYWORDS: frozenset[str] = frozenset(
    {
        "accident",
        "injury",
        "injured",
        "death",
        "killed",
        "fatality",
        "fire",
        "spill",
        "hazmat",
        "hazardous",
        "medical emergency",
        "collapsed",
        "hospitalized",
        "chemical leak",
        "tanker explosion",
        "overturned",
        "cargo damage",
    }
)

# Confidence threshold below which human approval is required.
_CONFIDENCE_THRESHOLD = 0.7


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------


def _before_agent(callback_context: CallbackContext) -> None:
    """Stamp a monotonic start time for duration tracking."""
    callback_context.state[_STATE_START] = time.perf_counter_ns()


def _after_model(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> None:
    """Accumulate Gemini token usage across both fetcher and formatter."""
    usage = getattr(llm_response, "usage_metadata", None)
    prev_in = callback_context.state.get(_STATE_TOKENS_IN, 0)
    prev_out = callback_context.state.get(_STATE_TOKENS_OUT, 0)
    callback_context.state[_STATE_TOKENS_IN] = prev_in + (
        getattr(usage, "prompt_token_count", 0) or 0
    )
    callback_context.state[_STATE_TOKENS_OUT] = prev_out + (
        getattr(usage, "candidates_token_count", 0) or 0
    )


def _clear_history(
    _callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> None:
    """Clear conversation history for the formatter to save tokens.

    The formatter only needs ``{triage:raw_exception_data}`` from state, not
    the full fetcher conversation. Per ADK discussion #3457.
    """
    if llm_request is not None:
        llm_request.contents = []


def _after_agent(callback_context: CallbackContext) -> None:
    """Post-classification: severity clamp, safety check, confidence gate, log."""
    start_ns = callback_context.state.get(_STATE_START)
    duration_ms = (time.perf_counter_ns() - start_ns) / 1_000_000 if start_ns is not None else 0.0

    # Apply deterministic overrides to the classification result in state.
    raw_classification = callback_context.state.get("triage:classification")
    if raw_classification and isinstance(raw_classification, str):
        _apply_post_classification_rules(callback_context, raw_classification)

    log_agent_invocation(
        agent_name=_AGENT_NAME,
        duration_ms=duration_ms,
        tokens_in=callback_context.state.get(_STATE_TOKENS_IN),
        tokens_out=callback_context.state.get(_STATE_TOKENS_OUT),
        model=_MODEL,
    )


def _apply_post_classification_rules(
    callback_context: CallbackContext,
    raw_json: str,
) -> None:
    """Apply deterministic severity clamp, confidence gate, and safety scan."""
    try:
        data: dict[str, Any] = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return

    modified = False
    exception_type = data.get("exception_type", "")
    severity = data.get("severity", "MEDIUM")
    confidence = data.get("confidence", 1.0)

    # Rule: safety_incident -> always CRITICAL
    if exception_type == "safety_incident" and severity != "CRITICAL":
        data["severity"] = Severity.CRITICAL.value
        modified = True

    # Rule: regulatory_compliance -> minimum HIGH
    is_regulatory = exception_type == "regulatory_compliance"
    if is_regulatory and _SEVERITY_ORDER.get(severity, 0) < _SEVERITY_ORDER["HIGH"]:
        data["severity"] = Severity.HIGH.value
        modified = True

    # Rule: confidence below threshold -> human approval
    if confidence < _CONFIDENCE_THRESHOLD and not data.get("requires_human_approval"):
        data["requires_human_approval"] = True
        modified = True

    # Rule: safety keywords in raw exception data -> force escalation
    raw_data = callback_context.state.get("triage:raw_exception_data", "")
    if isinstance(raw_data, str):
        raw_lower = raw_data.lower()
        matched = [kw for kw in _SAFETY_KEYWORDS if kw in raw_lower]
        if matched and not data.get("safety_escalation"):
            data["safety_escalation"] = {
                "trigger_type": "keyword_detection",
                "matched_terms": matched,
                "escalation_reason": "Safety keywords detected in exception data",
            }
            data["requires_human_approval"] = True
            if _SEVERITY_ORDER.get(data.get("severity", ""), 0) < _SEVERITY_ORDER["CRITICAL"]:
                data["severity"] = Severity.CRITICAL.value
            modified = True

    if modified:
        callback_context.state["triage:classification"] = json.dumps(data)


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------


def create_classifier() -> SequentialAgent:
    """Create the classifier SequentialAgent (fetcher + formatter).

    Returns:
        SequentialAgent wrapping fetcher and formatter sub-agents.
    """
    fetcher = LlmAgent(
        name="classifier_fetcher",
        model=_MODEL,
        description="Retrieves exception event and company context from Firestore.",
        instruction=_FETCHER_INSTRUCTION,
        tools=[get_exception_event, get_company_profile],
        output_key="triage:raw_exception_data",
        generate_content_config=genai_types.GenerateContentConfig(
            thinking_config=genai_types.ThinkingConfig(thinking_budget=1024),
            temperature=0.0,
        ),
        after_model_callback=_after_model,
    )

    formatter = LlmAgent(
        name="classifier_formatter",
        model=_MODEL,
        description="Classifies the exception into type, severity, and extracts key facts.",
        instruction=_FORMATTER_INSTRUCTION + "\n\nException briefing:\n{triage:raw_exception_data}",
        output_schema=ClassificationResult,
        output_key="triage:classification",
        include_contents="none",
        generate_content_config=genai_types.GenerateContentConfig(
            thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
            temperature=0.0,
        ),
        before_model_callback=_clear_history,
        after_model_callback=_after_model,
    )

    return SequentialAgent(
        name=_AGENT_NAME,
        description=(
            "Classifies logistics exceptions by type and severity. "
            "Uses a two-agent pattern: fetcher retrieves data, formatter produces "
            "structured ClassificationResult."
        ),
        sub_agents=[fetcher, formatter],
        before_agent_callback=_before_agent,
        after_agent_callback=_after_agent,
    )


# ADK discovery — `adk web` looks for `root_agent` at module level.
root_agent = create_classifier()

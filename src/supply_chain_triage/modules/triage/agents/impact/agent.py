"""Impact agent -- two-agent pattern (fetcher + formatter).

The fetcher calls tools to retrieve affected shipments, customer profiles,
route/hub data, and compute financial impact. The formatter applies
``output_schema=ImpactResult`` to produce structured output with priority
reasoning.  Wired as ``SequentialAgent`` per ``.claude/rules/agents.md`` S5.

Uses factory function ``create_impact()`` per ADK cheatsheet guidance to
avoid "agent already has parent" errors in multi-agent compositions.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from google.adk.agents import LlmAgent, SequentialAgent
from google.genai import types as genai_types

from supply_chain_triage.core.llm import get_resolved_llm_model
from supply_chain_triage.modules.triage.agents.impact.tools import (
    calculate_financial_impact,
    get_affected_shipments,
    get_customer_profile,
    get_exception_event,
    get_route_and_hub_status,
    get_shipment_details,
)
from supply_chain_triage.modules.triage.models.impact import ImpactResult
from supply_chain_triage.utils.logging import log_agent_invocation

if TYPE_CHECKING:
    from collections.abc import Callable

    from google.adk.agents.callback_context import CallbackContext
    from google.adk.models.llm_request import LlmRequest
    from google.adk.models.llm_response import LlmResponse

_AGENT_NAME = "impact"
_RESOLVED_MODEL = get_resolved_llm_model()
_MODEL = _RESOLVED_MODEL.model
_MODEL_NAME = _RESOLVED_MODEL.model_name
_PROMPTS_DIR = Path(__file__).parent / "prompts"
_FETCHER_INSTRUCTION = (_PROMPTS_DIR / "system_fetcher.md").read_text(encoding="utf-8")
_FORMATTER_INSTRUCTION = (_PROMPTS_DIR / "system_formatter.md").read_text(encoding="utf-8")

# State keys -- temp: prefix ensures no leakage to persisted session state.
_STATE_START = f"temp:{_AGENT_NAME}:start_perf_ns"
_STATE_TOKENS_IN = f"temp:{_AGENT_NAME}:tokens_in"
_STATE_TOKENS_OUT = f"temp:{_AGENT_NAME}:tokens_out"

# 5-factor priority weights for post-processing.
_W_VALUE = 0.20
_W_PENALTY = 0.20
_W_CHURN = 0.25
_W_FACILITY = 0.15
_W_CASCADE = 0.20

# Churn risk base scores.
_CHURN_BASE: dict[str, float] = {"LOW": 0.2, "MEDIUM": 0.5, "HIGH": 0.8}

# Customer tier bonus for churn factor.
_TIER_BONUS: dict[str, float] = {"new": 0.2, "high_value": 0.1}

# Hub congestion severity scores.
_CONGESTION_SCORE: dict[str, float] = {
    "CRITICAL": 1.0,
    "HIGH": 0.8,
    "MODERATE": 0.5,
    "LOW": 0.2,
}

# Hard-override deadline thresholds (hours).
_DEADLINE_URGENT_HOURS = 24
_DEADLINE_CRITICAL_HOURS = 6

# Hard-override score bumps.
_BUMP_PUBLIC_FACING = 0.3
_BUMP_URGENT_DEADLINE = 0.2
_BUMP_CRITICAL_DEADLINE = 0.4

# Score clamp range.
_SCORE_MAX = 2.0


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
    callback_context: CallbackContext,  # noqa: ARG001
    llm_request: LlmRequest,
) -> None:
    """Clear conversation history for the formatter to save tokens.

    The formatter only needs ``{raw_impact_data}`` from state, not
    the full fetcher conversation. Per ADK discussion #3457.
    """
    if llm_request is not None:
        llm_request.contents = []


def _after_agent(callback_context: CallbackContext) -> None:
    """Post-impact: compute priority weights, re-sort shipments, log."""
    start_ns = callback_context.state.get(_STATE_START)
    duration_ms = (time.perf_counter_ns() - start_ns) / 1_000_000 if start_ns is not None else 0.0

    raw_impact = callback_context.state.get("triage:impact")
    if raw_impact and isinstance(raw_impact, str):
        _apply_priority_weights(callback_context, raw_impact)

    log_agent_invocation(
        agent_name=_AGENT_NAME,
        duration_ms=duration_ms,
        tokens_in=callback_context.state.get(_STATE_TOKENS_IN),
        tokens_out=callback_context.state.get(_STATE_TOKENS_OUT),
        model=_MODEL_NAME,
    )


def _apply_priority_weights(
    callback_context: CallbackContext,
    raw_json: str,
) -> None:
    """Compute 5-factor priority scores, apply hard overrides, re-sort."""
    try:
        data: dict[str, Any] = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return
    shipments: list[dict[str, Any]] = data.get("affected_shipments", [])
    if not shipments:
        return

    max_value = max((s.get("value_inr", 0) for s in shipments), default=1) or 1
    max_penalty = max((s.get("penalty_amount_inr", 0) or 0 for s in shipments), default=1) or 1

    weights_record: dict[str, dict[str, Any]] = {}
    for shipment in shipments:
        sid = shipment.get("shipment_id", "")

        value_norm = shipment.get("value_inr", 0) / max_value
        penalty_norm = (shipment.get("penalty_amount_inr", 0) or 0) / max_penalty

        churn_base = _CHURN_BASE.get(shipment.get("churn_risk", "MEDIUM"), 0.5)
        tier = shipment.get("customer_tier", "")
        churn_score = min(churn_base + _TIER_BONUS.get(tier, 0.0), 1.0)

        hub_risk = data.get("hub_congestion_risk", "LOW") or "LOW"
        facility_score = _CONGESTION_SCORE.get(hub_risk, 0.2)

        remaining = shipment.get("remaining_route_legs")
        current = shipment.get("current_route_leg")
        if remaining is not None and current is not None and (remaining + current) > 0:
            cascade_score = remaining / (remaining + current)
        else:
            cascade_score = 0.5

        weighted = (
            _W_VALUE * value_norm
            + _W_PENALTY * penalty_norm
            + _W_CHURN * churn_score
            + _W_FACILITY * facility_score
            + _W_CASCADE * cascade_score
        )

        if shipment.get("public_facing_deadline"):
            weighted += _BUMP_PUBLIC_FACING

        hours = shipment.get("hours_until_deadline")
        if hours is not None:
            if hours < _DEADLINE_URGENT_HOURS:
                weighted += _BUMP_URGENT_DEADLINE
            if hours < _DEADLINE_CRITICAL_HOURS:
                weighted += _BUMP_CRITICAL_DEADLINE

        weighted = min(max(weighted, 0.0), _SCORE_MAX)

        weights_record[sid] = {
            "value": round(value_norm, 4),
            "penalty": round(penalty_norm, 4),
            "churn": round(churn_score, 4),
            "facility_impact": round(facility_score, 4),
            "cascade": round(cascade_score, 4),
            "hard_overrides_applied": _hard_override_labels(shipment),
            "final_score": round(weighted, 4),
        }

    sorted_ids = sorted(
        weights_record,
        key=lambda sid: weights_record[sid]["final_score"],
        reverse=True,
    )
    data["recommended_priority_order"] = sorted_ids

    callback_context.state["triage:impact_weights"] = json.dumps(weights_record)
    callback_context.state["triage:impact"] = json.dumps(data)


def _hard_override_labels(shipment: dict[str, Any]) -> list[str]:
    """Return human-readable labels for hard overrides applied to a shipment."""
    labels: list[str] = []
    if shipment.get("public_facing_deadline"):
        labels.append("public_facing_deadline")
    hours = shipment.get("hours_until_deadline")
    if hours is not None:
        if hours < _DEADLINE_CRITICAL_HOURS:
            labels.append("hours_until_deadline_lt_6")
        elif hours < _DEADLINE_URGENT_HOURS:
            labels.append("hours_until_deadline_lt_24")
    return labels


def _make_combined_before(
    rule_check: Callable[[CallbackContext], genai_types.Content | None],
) -> Callable[[CallbackContext], genai_types.Content | None]:
    """Compose an upstream rule check with the timing stamp.

    The rule check fires first. If it returns ``Content``, the agent will be
    skipped by ADK, so we also skip the timing stamp (no point timing an agent
    that won't run). If the rule check returns ``None``, we stamp the start
    time for duration logging and let the agent proceed.
    """

    def _combined(callback_context: CallbackContext) -> genai_types.Content | None:
        result = rule_check(callback_context)
        if result is not None:
            return result
        _before_agent(callback_context)
        return None

    return _combined


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------


def create_impact(
    before_agent_callback: Callable[[CallbackContext], genai_types.Content | None] | None = None,
) -> SequentialAgent:
    """Create the impact SequentialAgent (fetcher + formatter).

    Args:
        before_agent_callback: Optional upstream callback (e.g., Rule C/F gate).
            When provided, it fires before the timing stamp and can short-circuit
            the agent by returning ``Content``. When ``None``, only the built-in
            timing stamp runs.

    Returns:
        SequentialAgent wrapping fetcher and formatter sub-agents.
    """
    fetcher = LlmAgent(
        name="impact_fetcher",
        model=_MODEL,
        description=(
            "Retrieves affected shipments, customer profiles, route/hub data, "
            "and computes financial impact."
        ),
        instruction=_FETCHER_INSTRUCTION,
        tools=[
            get_exception_event,
            get_affected_shipments,
            get_shipment_details,
            get_customer_profile,
            get_route_and_hub_status,
            calculate_financial_impact,
        ],
        output_key="raw_impact_data",
        generate_content_config=genai_types.GenerateContentConfig(
            thinking_config=genai_types.ThinkingConfig(thinking_budget=1024),
            temperature=0.0,
        ),
        after_model_callback=_after_model,
    )

    formatter = LlmAgent(
        name="impact_formatter",
        model=_MODEL,
        description=(
            "Synthesises impact data into structured ImpactResult with priority reasoning."
        ),
        instruction=(
            "Assess impact:\n\n{raw_impact_data}\n\n"
            "Classification:\n\n{triage:classification}\n\n" + _FORMATTER_INSTRUCTION
        ),
        output_schema=ImpactResult,
        output_key="triage:impact",
        include_contents="none",
        generate_content_config=genai_types.GenerateContentConfig(
            thinking_config=genai_types.ThinkingConfig(thinking_budget=1024),
            temperature=0.0,
        ),
        before_model_callback=_clear_history,
        after_model_callback=_after_model,
    )

    pipeline_before = (
        _make_combined_before(before_agent_callback)
        if before_agent_callback is not None
        else _before_agent
    )

    return SequentialAgent(
        name=_AGENT_NAME,
        description=(
            "Assesses business impact of classified exceptions. "
            "Uses a two-agent pattern: fetcher retrieves shipment/customer/route "
            "data, formatter produces structured ImpactResult with priority ordering."
        ),
        sub_agents=[fetcher, formatter],
        before_agent_callback=pipeline_before,
        after_agent_callback=_after_agent,
    )


# ADK discovery -- `adk web` looks for `root_agent` at module level.
root_agent = create_impact()

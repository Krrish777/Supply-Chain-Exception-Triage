"""Triage runner — blocking entry point for the full triage pipeline.

Seeds ``triage:event_id`` + ``triage:event_raw_text`` into session state before
dispatch (so Rule B's keyword scan fires with state populated), drains
``Runner.run_async`` events, then assembles a ``TriageResult`` from the final
session state.

Day 3 scope: blocking path only. The SSE streaming runner (Day 4) reuses the
same pipeline factory but yields events progressively.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types
from pydantic import ValidationError

from supply_chain_triage.modules.triage.models.classification import ClassificationResult
from supply_chain_triage.modules.triage.models.common_types import (
    EscalationPriority,
    TriageStatus,
)
from supply_chain_triage.modules.triage.models.impact import ImpactResult
from supply_chain_triage.modules.triage.models.triage_result import TriageResult
from supply_chain_triage.modules.triage.pipeline import create_triage_pipeline
from supply_chain_triage.utils.logging import get_logger, log_agent_invocation

if TYPE_CHECKING:
    from collections.abc import Mapping

logger = get_logger(__name__)

_APP_NAME = "triage_runner"
_USER_ID = "triage_user"
_NS_TO_MS = 1_000_000
_PIPELINE_AGENT_NAME = "triage_pipeline"


async def run_triage(*, event_id: str, raw_text: str) -> TriageResult:
    """Run the full triage pipeline and return a structured ``TriageResult``.

    Seeds ``triage:event_id`` and ``triage:event_raw_text`` into session state
    at session-creation time (guaranteed committed before the first
    ``before_agent_callback`` fires) and reads the final state after the
    pipeline drains.

    Args:
        event_id: Exception event ID (Firestore doc ID).
        raw_text: Raw text of the exception (body of the Rule B keyword scan).

    Returns:
        A ``TriageResult`` assembled from session state. Never raises on
        expected pipeline outcomes (Rule B / C / F skip, parse errors) — those
        surface via ``status`` + ``errors``.
    """
    start_ns = time.perf_counter_ns()

    session_service = InMemorySessionService()  # type: ignore[no-untyped-call]
    pipeline = create_triage_pipeline()
    runner = Runner(agent=pipeline, app_name=_APP_NAME, session_service=session_service)

    session = await session_service.create_session(
        app_name=_APP_NAME,
        user_id=_USER_ID,
        state={
            "triage:event_id": event_id,
            "triage:event_raw_text": raw_text,
        },
    )

    trigger = genai_types.Content(
        role="user",
        parts=[genai_types.Part.from_text(text=f"Triage exception {event_id}")],
    )
    async for _event in runner.run_async(
        user_id=_USER_ID, session_id=session.id, new_message=trigger
    ):
        pass

    updated_session = await session_service.get_session(
        app_name=_APP_NAME, user_id=_USER_ID, session_id=session.id
    )
    state: Mapping[str, object] = updated_session.state if updated_session else {}

    duration_ms = (time.perf_counter_ns() - start_ns) // _NS_TO_MS
    result = _assemble_triage_result(event_id=event_id, state=state, duration_ms=int(duration_ms))

    # Cost-attribution + lifecycle log line. `audit_event` is deferred to Day 5
    # when the HTTP route + auth middleware supply the required correlation_id /
    # user_id / company_id kwargs (see .claude/rules/observability.md §6).
    log_agent_invocation(
        agent_name=_PIPELINE_AGENT_NAME,
        duration_ms=float(duration_ms),
        status=result.status.value,
        event_id=event_id,
        error_count=len(result.errors),
    )

    return result


def _assemble_triage_result(
    *,
    event_id: str,
    state: Mapping[str, object],
    duration_ms: int,
) -> TriageResult:
    """Build a ``TriageResult`` from the final session state of a pipeline run."""
    errors: list[str] = []
    classification = _parse_classification(state, errors)
    impact = _parse_impact(state, errors)
    status = _resolve_status(state, classification=classification, impact=impact, errors=errors)
    summary = _make_summary(state, classification=classification, impact=impact)
    escalation_priority = _parse_escalation_priority(state)

    return TriageResult(
        event_id=event_id,
        status=status,
        coordinator_trace=[],
        classification=classification,
        impact=impact,
        summary=summary,
        processing_time_ms=max(duration_ms, 0),
        errors=errors,
        escalation_priority=escalation_priority,
    )


def _parse_classification(
    state: Mapping[str, object], errors: list[str]
) -> ClassificationResult | None:
    """Parse ``triage:classification`` JSON from state; record parse errors."""
    raw = state.get("triage:classification")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return ClassificationResult.model_validate_json(raw)
    except (ValidationError, json.JSONDecodeError) as exc:
        errors.append(f"classification_parse_error: {exc.__class__.__name__}")
        return None


def _parse_impact(state: Mapping[str, object], errors: list[str]) -> ImpactResult | None:
    """Parse ``triage:impact`` JSON from state; record parse errors.

    Returns ``None`` when the key is absent (Rule B / F skip is a valid outcome,
    not an error) or when parsing fails (caller flips status to ``partial``).
    """
    raw = state.get("triage:impact")
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return ImpactResult.model_validate_json(raw)
    except (ValidationError, json.JSONDecodeError) as exc:
        errors.append(f"impact_parse_error: {exc.__class__.__name__}")
        return None


def _resolve_status(
    state: Mapping[str, object],
    *,
    classification: ClassificationResult | None,
    impact: ImpactResult | None,  # noqa: ARG001 — reserved for future partial-detection logic
    errors: list[str],
) -> TriageStatus:
    """Resolve the final ``TriageStatus`` from state, classification, and errors."""
    raw_status = state.get("triage:status", "complete")
    status_str = raw_status if isinstance(raw_status, str) else "complete"
    try:
        status = TriageStatus(status_str)
    except ValueError:
        status = TriageStatus.complete

    if errors and status == TriageStatus.complete:
        status = TriageStatus.partial

    if (
        status == TriageStatus.complete
        and classification is not None
        and classification.requires_human_approval
    ):
        status = TriageStatus.escalated_to_human

    return status


def _parse_escalation_priority(state: Mapping[str, object]) -> EscalationPriority | None:
    """Map ``triage:escalation_priority`` from state, or ``None`` if unset/unknown."""
    raw = state.get("triage:escalation_priority")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return EscalationPriority(raw)
    except ValueError:
        return None


def _make_summary(
    state: Mapping[str, object],
    *,
    classification: ClassificationResult | None,
    impact: ImpactResult | None,
) -> str:
    """Generate a one-line human-readable summary of the triage outcome."""
    if classification is None:
        return "Triage incomplete — classification unavailable."

    sev = classification.severity
    exc_type = classification.exception_type

    if state.get("triage:rule_b_applied"):
        return f"{sev} {exc_type} — safety escalation triggered. Impact skipped."
    if state.get("triage:rule_f_applied"):
        return f"{sev} {exc_type} — Impact skipped (Rule F, LOW severity)."
    if impact is None:
        return f"{sev} {exc_type} — Impact unavailable."

    shipment_count = len(impact.affected_shipments)
    return f"{sev} {exc_type} — {shipment_count} shipment(s) assessed."

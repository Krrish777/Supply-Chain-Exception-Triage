"""Triage runner — blocking + streaming entry points for the full triage pipeline.

Seeds ``triage:event_id`` + ``triage:event_raw_text`` into session state before
dispatch (so Rule B's keyword scan fires with state populated), drains
``Runner.run_async`` events, then assembles a ``TriageResult`` from the final
session state.

Day 3 delivered ``run_triage`` (blocking). Day 4 adds ``_triage_event_stream``
which reuses the same pipeline factory but yields SSE-friendly frame dicts
progressively. Both entry points share ``_assemble_triage_result`` and the
parse helpers below.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

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
    from collections.abc import AsyncIterator, Iterator, Mapping

    from google.adk.events import Event

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

    state = await _get_session_state(session_service, session.id)
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


# ---------------------------------------------------------------------------
# Day 4 — SSE streaming runner
# ---------------------------------------------------------------------------


@dataclass
class _StreamTracking:
    """Per-stream bookkeeping for frame-emission idempotence."""

    started_agents: set[str] = field(default_factory=set)
    emitted_partial_classification: bool = False


async def _triage_event_stream(*, event_id: str, raw_text: str) -> AsyncIterator[dict[str, Any]]:
    r"""Stream the triage pipeline as SSE-friendly frame dicts.

    Reuses ``create_triage_pipeline()`` (same pipeline as ``run_triage``) and
    translates ADK events into a stable 7-type frame contract decoupled from
    ADK's internal ``Event`` shape (see ``.claude/rules/agents.md`` §10).

    Frame contract (per Sprint 3 PRD §2.2):
        ``agent_started`` / ``tool_invoked`` / ``agent_completed`` /
        ``partial_result`` / ``complete`` / ``error`` / ``done``.

    Args:
        event_id: Exception event ID (Firestore doc ID, or synthesized ad-hoc).
        raw_text: Raw text of the exception (body of Rule B's keyword scan).

    Yields:
        ``{"event": <type>, "data": <payload dict>}``. The route layer wraps
        each dict with SSE framing (``event: X\ndata: <json>\n\n``).

    Never 500s: on any exception an ``error`` frame is emitted before ``done``.
    ``asyncio.CancelledError`` propagates (consumer is gone — ``done`` is not
    emitted after cancel).
    """
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

    tracking = _StreamTracking()
    start_ns = time.perf_counter_ns()

    try:
        async for event in runner.run_async(
            user_id=_USER_ID, session_id=session.id, new_message=trigger
        ):
            state = await _get_session_state(session_service, session.id)
            for frame in _frames_for_event(event, state, tracking):
                yield frame

        state = await _get_session_state(session_service, session.id)
        yield _make_complete_frame(event_id=event_id, state=state, start_ns=start_ns)
    except Exception as exc:  # SSE stream must never 500 — always terminate with frames
        yield {
            "event": "error",
            "data": {"code": exc.__class__.__name__, "message": str(exc)[:200]},
        }

    yield {"event": "done", "data": {}}


def _frames_for_event(
    event: Event,
    state: Mapping[str, object],
    tracking: _StreamTracking,
) -> Iterator[dict[str, Any]]:
    """Translate one ADK event into zero-or-more SSE frame dicts.

    Emits ``agent_started`` on first appearance of an author, one
    ``tool_invoked`` per function call, ``agent_completed`` on the final
    event of each author's turn, and ``partial_result`` the first time
    ``triage:classification`` appears in state.
    """
    author = event.author or _PIPELINE_AGENT_NAME

    if author not in tracking.started_agents:
        tracking.started_agents.add(author)
        yield {"event": "agent_started", "data": {"agent_name": author}}

    for fn_call in event.get_function_calls() or []:
        yield {
            "event": "tool_invoked",
            "data": {"tool_name": fn_call.name, "agent_name": author},
        }

    if event.is_final_response():
        status = "escalated" if state.get("triage:rule_b_applied") else "ok"
        yield {
            "event": "agent_completed",
            "data": {"agent_name": author, "status": status},
        }

    if not tracking.emitted_partial_classification:
        raw = state.get("triage:classification")
        if isinstance(raw, str) and raw:
            try:
                value: Any = json.loads(raw)
            except json.JSONDecodeError:
                value = None
            tracking.emitted_partial_classification = True
            yield {
                "event": "partial_result",
                "data": {"key": "classification", "value": value},
            }


def _make_complete_frame(
    *, event_id: str, state: Mapping[str, object], start_ns: int
) -> dict[str, Any]:
    """Assemble the terminal ``complete`` frame + log invocation lifecycle."""
    duration_ms = (time.perf_counter_ns() - start_ns) // _NS_TO_MS
    result = _assemble_triage_result(event_id=event_id, state=state, duration_ms=int(duration_ms))
    log_agent_invocation(
        agent_name=_PIPELINE_AGENT_NAME,
        duration_ms=float(duration_ms),
        status=result.status.value,
        event_id=event_id,
        error_count=len(result.errors),
    )
    return {
        "event": "complete",
        "data": {"triage_result": result.model_dump(mode="json")},
    }


async def _get_session_state(
    session_service: InMemorySessionService, session_id: str
) -> Mapping[str, object]:
    """Fetch the current session state, or an empty mapping if the session vanished."""
    session = await session_service.get_session(
        app_name=_APP_NAME, user_id=_USER_ID, session_id=session_id
    )
    return session.state if session else {}


# ---------------------------------------------------------------------------
# Shared assembly helpers
# ---------------------------------------------------------------------------


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

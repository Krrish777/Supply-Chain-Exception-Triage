"""Deterministic event hydration callback for the triage pipeline.

Runs as the FIRST ``before_agent_callback`` on the pipeline ``SequentialAgent``
(before Rule B). Pre-fetches the exception event and company profile from
Firestore so:

1. Rule B can scan the actual ``raw_content`` (not the empty ``raw_text``
   that the API supplies when only ``event_id`` is given).
2. The classifier and impact agents read hydrated state via
   ``{triage:event_raw_content?}`` / ``{triage:company_markdown?}`` template
   substitution instead of relying on the LLM to choose the right tools.

Two input modes are supported:

- **Path A — structured event ID** (matches a real Firestore document, i.e.
  not an ``adhoc-...`` synthetic ID): fetch the event from Firestore, write
  its ``raw_content`` + ``metadata`` into state, and re-seed
  ``triage:event_raw_text`` so Rule B sees the real content.
- **Path B — natural-language input** (no event ID, or synthetic
  ``adhoc-...`` ID from the API): copy ``triage:event_raw_text`` into
  ``triage:event_raw_content`` so the same prompt template works for both
  paths. No Firestore event lookup.

Company hydration runs in both paths: prefer ``metadata.company_id`` from
the fetched event (Path A); fall back to ``triage:auth_company_id`` seeded
by the runner from authenticated user claims (Path B).

Tool failures set ``triage:hydration_error`` (non-empty string) and the
pipeline continues — classifier prompts read ``{triage:event_raw_content?}``
with optional substitution and degrade gracefully.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from supply_chain_triage.modules.triage.tools.lookup import (
    get_company_profile,
    get_exception_event,
)
from supply_chain_triage.utils.logging import get_logger

if TYPE_CHECKING:
    from google.adk.agents.callback_context import CallbackContext

logger = get_logger(__name__)

# State keys hydration writes. Kept as module-level constants so tests and
# downstream prompts have a single source of truth.
_STATE_EVENT_ID = "triage:event_id"
_STATE_EVENT_RAW_TEXT = "triage:event_raw_text"
_STATE_AUTH_COMPANY_ID = "triage:auth_company_id"
_STATE_EVENT_RAW_CONTENT = "triage:event_raw_content"
_STATE_EVENT_METADATA = "triage:event_metadata"
_STATE_COMPANY_ID = "triage:company_id"
_STATE_COMPANY_DATA = "triage:company_data"
_STATE_COMPANY_MARKDOWN = "triage:company_markdown"
_STATE_HYDRATION_ERROR = "triage:hydration_error"

_ADHOC_PREFIX = "adhoc-"


def _is_real_event_id(event_id: str) -> bool:
    """True when ``event_id`` looks like a Firestore document, not a synth ID.

    Accepts any non-empty ID that does not start with the ``adhoc-`` prefix
    used by ``runners/routes/triage.py`` when the API caller supplies no
    ``event_id``.
    """
    return bool(event_id) and not event_id.startswith(_ADHOC_PREFIX)


async def _hydrate_event(callback_context: CallbackContext) -> None:
    """Pre-fetch event + company into state before any LLM call.

    See module docstring for the full Path A / Path B contract.
    """
    state = callback_context.state
    event_id = str(state.get(_STATE_EVENT_ID, "") or "")
    raw_text = str(state.get(_STATE_EVENT_RAW_TEXT, "") or "")

    # `get_exception_event` and `get_company_profile` only touch `.state` on
    # the context they receive — both `CallbackContext` and `ToolContext`
    # expose a compatible `.state` dict, so passing `callback_context`
    # directly is safe (duck-typed).
    company_id: str | None = None

    # ---- Path A: structured event ID -----------------------------------
    if _is_real_event_id(event_id):
        result = await get_exception_event(event_id, callback_context)
        if result.get("status") == "success":
            data = result.get("data") or {}
            raw_content = str(data.get("raw_content", "") or "")
            metadata: dict[str, Any] = data.get("metadata") or {}

            state[_STATE_EVENT_RAW_CONTENT] = raw_content
            state[_STATE_EVENT_METADATA] = metadata
            if raw_content:
                # Re-seed raw_text so Rule B's keyword scan sees real content.
                state[_STATE_EVENT_RAW_TEXT] = raw_content

            if isinstance(metadata, dict):
                meta_company = metadata.get("company_id")
                if isinstance(meta_company, str) and meta_company:
                    company_id = meta_company
        else:
            state[_STATE_HYDRATION_ERROR] = str(
                result.get("error_message") or "exception_lookup_failed"
            )
            # Path A failed: fall back to whatever raw_text was.
            state[_STATE_EVENT_RAW_CONTENT] = raw_text
    # ---- Path B: natural-language input --------------------------------
    else:
        state[_STATE_EVENT_RAW_CONTENT] = raw_text

    # ---- Company hydration (both paths) --------------------------------
    if not company_id:
        auth_company = state.get(_STATE_AUTH_COMPANY_ID)
        if isinstance(auth_company, str) and auth_company:
            company_id = auth_company

    if company_id:
        company_result = await get_company_profile(company_id, callback_context)
        if company_result.get("status") == "success":
            state[_STATE_COMPANY_ID] = company_id
            state[_STATE_COMPANY_DATA] = company_result.get("data") or {}
            state[_STATE_COMPANY_MARKDOWN] = str(company_result.get("markdown", "") or "")
        else:
            # Preserve any pre-existing event-side error.
            state.setdefault(
                _STATE_HYDRATION_ERROR,
                str(company_result.get("error_message") or "company_lookup_failed"),
            )

    logger.info(
        "triage_hydrated",
        event_id=event_id or "(none)",
        path="A" if _is_real_event_id(event_id) else "B",
        company_id=company_id or "(none)",
        has_raw_content=bool(state.get(_STATE_EVENT_RAW_CONTENT)),
        hydration_error=state.get(_STATE_HYDRATION_ERROR),
    )

    # Hydration NEVER returns Content — Rule B downstream is what short-circuits.

"""Classifier-private tools — Firestore lookups for the fetcher agent.

Per ``.claude/rules/tools.md``: async for I/O, return
``{"status": "success"|"error"|"retry", ...}``, per-turn cache in state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from supply_chain_triage.core.config import get_firestore_client
from supply_chain_triage.modules.triage.models.company_profile import CompanyProfile
from supply_chain_triage.modules.triage.models.exception_event import ExceptionEvent
from supply_chain_triage.utils.logging import get_logger, log_firestore_op

if TYPE_CHECKING:
    from google.adk.tools import ToolContext  # type: ignore[attr-defined]

logger = get_logger(__name__)

# Firestore collection names
_EXCEPTIONS_COLLECTION = "exceptions"
_COMPANIES_COLLECTION = "companies"


async def get_exception_event(
    event_id: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Retrieve an exception event by ID from Firestore.

    Args:
        event_id: Firestore document ID for the exception event.
        tool_context: ADK tool context (provides state + actions).

    Returns:
        ``{"status": "success", "data": {...}}`` on hit,
        ``{"status": "error", "error_message": str}`` on miss or failure.
    """
    cache_key = f"cache:exception:{event_id}"
    if cached := tool_context.state.get(cache_key):
        return {"status": "success", "data": cached}

    try:
        db = get_firestore_client()
        doc = await db.collection(_EXCEPTIONS_COLLECTION).document(event_id).get()

        if not doc.exists:
            return {
                "status": "error",
                "error_message": f"Exception event {event_id!r} not found",
            }

        raw = doc.to_dict() or {}
        raw["event_id"] = doc.id
        event = ExceptionEvent.model_validate(raw)
        data = event.model_dump(mode="json")

        log_firestore_op(
            op="get",
            collection=_EXCEPTIONS_COLLECTION,
            doc_count=1,
            duration_ms=0,
        )

        tool_context.state[cache_key] = data
        return {"status": "success", "data": data}

    except Exception as exc:
        logger.error(
            "tool_failed",
            tool_name="get_exception_event",
            error_class=type(exc).__name__,
        )
        return {
            "status": "error",
            "error_message": f"Failed to fetch exception: {type(exc).__name__}",
        }


async def get_company_profile(
    company_id: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Retrieve a company profile by ID from Firestore.

    Args:
        company_id: Firestore document ID for the company.
        tool_context: ADK tool context (provides state + actions).

    Returns:
        ``{"status": "success", "data": {...}, "markdown": str}`` on hit,
        ``{"status": "error", "error_message": str}`` on miss or failure.
    """
    cache_key = f"cache:company:{company_id}"
    if cached := tool_context.state.get(cache_key):
        return {"status": "success", "data": cached["data"], "markdown": cached["markdown"]}

    try:
        db = get_firestore_client()
        doc = await db.collection(_COMPANIES_COLLECTION).document(company_id).get()

        if not doc.exists:
            return {
                "status": "error",
                "error_message": f"Company {company_id!r} not found",
            }

        raw = doc.to_dict() or {}
        raw["company_id"] = doc.id
        profile = CompanyProfile.model_validate(raw)
        data = profile.model_dump(mode="json")
        markdown = profile.to_markdown()

        log_firestore_op(
            op="get",
            collection=_COMPANIES_COLLECTION,
            doc_count=1,
            duration_ms=0,
        )

        tool_context.state[cache_key] = {"data": data, "markdown": markdown}
        return {"status": "success", "data": data, "markdown": markdown}

    except Exception as exc:
        logger.error(
            "tool_failed",
            tool_name="get_company_profile",
            error_class=type(exc).__name__,
        )
        return {
            "status": "error",
            "error_message": f"Failed to fetch company: {type(exc).__name__}",
        }

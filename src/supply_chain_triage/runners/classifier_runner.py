"""Standalone classifier endpoint for Tier 1 testing.

Accepts ``POST /api/v1/classify`` with ``{"event_id": "..."}`` and returns the
``ClassificationResult`` from the classifier agent. No auth for Tier 1 — add
when the Coordinator sprint wires this into the full pipeline.

Usage:
    uvicorn supply_chain_triage.runners.classifier_runner:app --reload
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

from supply_chain_triage.modules.triage.agents.classifier.agent import create_classifier
from supply_chain_triage.modules.triage.agents.classifier.schemas import (
    ClassifierInput,  # noqa: TC001 — runtime-needed by FastAPI body validation
)
from supply_chain_triage.utils.logging import get_logger

logger = get_logger(__name__)

app = FastAPI(title="Classifier API", version="0.1.0")
_session_service = InMemorySessionService()  # type: ignore[no-untyped-call]
_APP_NAME = "classifier_test"
_USER_ID = "test_user"


@app.post("/api/v1/classify")
async def classify_exception(*, payload: ClassifierInput) -> dict[str, Any]:
    """Classify a logistics exception by event ID.

    Args:
        payload: Request body with ``event_id``.

    Returns:
        Classification result dict from the agent.
    """
    classifier = create_classifier()
    runner = Runner(
        agent=classifier,
        app_name=_APP_NAME,
        session_service=_session_service,
    )

    session = await _session_service.create_session(
        app_name=_APP_NAME,
        user_id=_USER_ID,
    )

    result_text = ""
    async for event in runner.run_async(
        user_id=_USER_ID,
        session_id=session.id,
        new_message=genai_types.Content(
            role="user",
            parts=[
                genai_types.Part.from_text(
                    text=f"Classify exception with event_id: {payload.event_id}",
                )
            ],
        ),
    ):
        if event.is_final_response() and event.content and event.content.parts:
            result_text = event.content.parts[0].text or ""

    # Also pull the structured classification from state if available.
    updated_session = await _session_service.get_session(
        app_name=_APP_NAME,
        user_id=_USER_ID,
        session_id=session.id,
    )
    classification = None
    if updated_session:
        classification = updated_session.state.get("triage:classification")

    return {
        "event_id": payload.event_id,
        "classification": classification,
        "raw_response": result_text,
    }


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check."""
    return {"status": "ok"}

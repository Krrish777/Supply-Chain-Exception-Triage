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
from google.adk.sessions import InMemorySessionService

from supply_chain_triage.modules.triage.agents.classifier.agent import create_classifier
from supply_chain_triage.modules.triage.agents.classifier.schemas import (
    ClassifierInput,  # noqa: TC001 — runtime-needed by FastAPI body validation
)
from supply_chain_triage.runners._shared import AgentEndpointConfig, run_agent_endpoint

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
    result = await run_agent_endpoint(
        agent=create_classifier(),
        session_service=_session_service,
        config=AgentEndpointConfig(
            app_name=_APP_NAME,
            user_id=_USER_ID,
            message_text=f"Classify exception with event_id: {payload.event_id}",
            state_key_map={"classification": "triage:classification"},
        ),
    )
    return {"event_id": payload.event_id, **result}


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check."""
    return {"status": "ok"}

"""Standalone impact endpoint for Tier 1 testing.

Accepts ``POST /api/v1/impact`` with ``{"event_id": "..."}`` and returns the
``ImpactResult`` from the impact agent. No auth for Tier 1 — add when the
Coordinator sprint wires this into the full pipeline.

Usage:
    uvicorn supply_chain_triage.runners.impact_runner:app --reload
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from google.adk.sessions import InMemorySessionService

from supply_chain_triage.modules.triage.agents.impact.agent import create_impact
from supply_chain_triage.modules.triage.agents.impact.schemas import (
    ImpactInput,  # noqa: TC001 — runtime-needed by FastAPI body validation
)
from supply_chain_triage.runners._shared import AgentEndpointConfig, run_agent_endpoint

app = FastAPI(title="Impact API", version="0.1.0")
_session_service = InMemorySessionService()  # type: ignore[no-untyped-call]
_APP_NAME = "impact_test"
_USER_ID = "test_user"


@app.post("/api/v1/impact")
async def assess_impact(*, payload: ImpactInput) -> dict[str, Any]:
    """Assess business impact of a logistics exception by event ID.

    Args:
        payload: Request body with ``event_id``.

    Returns:
        Impact assessment result dict from the agent.
    """
    result = await run_agent_endpoint(
        agent=create_impact(),
        session_service=_session_service,
        config=AgentEndpointConfig(
            app_name=_APP_NAME,
            user_id=_USER_ID,
            message_text=f"Assess impact for exception with event_id: {payload.event_id}",
            state_key_map={
                "impact": "triage:impact",
                "impact_weights": "triage:impact_weights",
            },
        ),
    )
    return {"event_id": payload.event_id, **result}


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check."""
    return {"status": "ok"}

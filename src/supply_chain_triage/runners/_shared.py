"""Shared helpers for small FastAPI runner endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from google.adk.runners import Runner
from google.genai import types as genai_types

if TYPE_CHECKING:
    from collections.abc import Mapping

    from google.adk.sessions import InMemorySessionService


@dataclass(frozen=True, slots=True)
class AgentEndpointConfig:
    """Configuration for a single-run agent endpoint."""

    app_name: str
    user_id: str
    message_text: str
    state_key_map: Mapping[str, str]


async def run_agent_endpoint(
    *,
    agent: Any,
    session_service: InMemorySessionService,
    config: AgentEndpointConfig,
) -> dict[str, Any]:
    """Run an agent once and return the final response plus selected state."""
    runner = Runner(agent=agent, app_name=config.app_name, session_service=session_service)
    session = await session_service.create_session(
        app_name=config.app_name,
        user_id=config.user_id,
    )

    result_text = ""
    async for event in runner.run_async(
        user_id=config.user_id,
        session_id=session.id,
        new_message=genai_types.Content(
            role="user",
            parts=[genai_types.Part.from_text(text=config.message_text)],
        ),
    ):
        if event.is_final_response() and event.content and event.content.parts:
            result_text = event.content.parts[0].text or ""

    updated_session = await session_service.get_session(
        app_name=config.app_name,
        user_id=config.user_id,
        session_id=session.id,
    )

    response: dict[str, Any] = {"raw_response": result_text}
    if updated_session is None:
        for response_key in config.state_key_map:
            response[response_key] = None
        return response

    for response_key, state_key in config.state_key_map.items():
        response[response_key] = updated_session.state.get(state_key)

    return response

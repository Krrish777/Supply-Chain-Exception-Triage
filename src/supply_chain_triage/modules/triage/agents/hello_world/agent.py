"""Hello-world ADK baseline agent used to smoke-test the ADK toolchain.

``adk web`` picks up ``root_agent`` and the agent responds to greetings in the
browser UI. The model and prompt live next to the agent so the baseline stays
easy to inspect and edit.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from google.adk.agents import LlmAgent

from supply_chain_triage.core.llm import get_resolved_llm_model
from supply_chain_triage.utils.logging import log_agent_invocation

if TYPE_CHECKING:
    from google.adk.agents.callback_context import CallbackContext
    from google.adk.models.llm_response import LlmResponse

_AGENT_NAME = "hello_world"
_RESOLVED_MODEL = get_resolved_llm_model()
_MODEL = _RESOLVED_MODEL.model
_MODEL_NAME = _RESOLVED_MODEL.model_name
_INSTRUCTION = (Path(__file__).parent / "prompts" / "hello_world.md").read_text(
    encoding="utf-8",
)

# Agent-local state keys avoid collisions in future SequentialAgent pipelines.
_STATE_START = f"temp:{_AGENT_NAME}:start_perf_ns"
_STATE_TOKENS_IN = f"temp:{_AGENT_NAME}:tokens_in"
_STATE_TOKENS_OUT = f"temp:{_AGENT_NAME}:tokens_out"


def _before_agent(callback_context: CallbackContext) -> None:
    """Stamp a monotonic start time so ``_after_agent`` can compute duration."""
    callback_context.state[_STATE_START] = time.perf_counter_ns()


def _after_model(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> None:
    """Capture Gemini token usage for cost attribution.

    Gemini reports usage on ``llm_response.usage_metadata``. Degrades to zeros
    if the field is missing (cached responses, older ADK) — better to log a
    zero than crash an invocation over telemetry.
    """
    usage = getattr(llm_response, "usage_metadata", None)
    callback_context.state[_STATE_TOKENS_IN] = getattr(usage, "prompt_token_count", 0) or 0
    callback_context.state[_STATE_TOKENS_OUT] = getattr(usage, "candidates_token_count", 0) or 0


def _after_agent(callback_context: CallbackContext) -> None:
    """Emit the mandatory ``agent_invoked`` event with duration + tokens."""
    start_ns = callback_context.state.get(_STATE_START)
    duration_ms = (time.perf_counter_ns() - start_ns) / 1_000_000 if start_ns is not None else 0.0
    log_agent_invocation(
        agent_name=_AGENT_NAME,
        duration_ms=duration_ms,
        tokens_in=callback_context.state.get(_STATE_TOKENS_IN),
        tokens_out=callback_context.state.get(_STATE_TOKENS_OUT),
        model=_MODEL_NAME,
    )


root_agent = LlmAgent(
    model=_MODEL,
    name=_AGENT_NAME,
    description=(
        "Baseline greeter agent. Smoke-tests the ADK toolchain end-to-end. "
        "Has no tools and no data access."
    ),
    instruction=_INSTRUCTION,
    before_agent_callback=_before_agent,
    after_model_callback=_after_model,
    after_agent_callback=_after_agent,
)

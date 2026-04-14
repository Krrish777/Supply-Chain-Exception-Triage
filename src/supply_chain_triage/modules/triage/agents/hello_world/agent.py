"""Hello-world ADK baseline agent.

Per Sprint 0 PRD v2 §2.7 + §17 item #3: validates the end-to-end ADK toolchain.
``adk web`` picks up ``root_agent`` and the agent responds to greetings in the
browser UI. Once this works, the real feature agents (Classifier Sprint 1,
Impact Sprint 2, Coordinator Sprint 3) extend the same pattern.

Architectural notes:
- Gemini model pinned to ``gemini-2.5-flash`` per ADR-001. Do NOT "upgrade" to
  a newer model without a follow-up ADR.
- Instruction text is read from the co-located ``prompts/hello_world.md`` at
  module import — keeps prompt + code edit-atomic without a build step.
- This file is the single approved spot for ``google.adk.*`` imports in this
  agent subpackage (per ``.claude/rules/imports.md`` + ruff ``TID251``
  per-file-ignore for ``modules/*/agents/**/agent.py``).
- Callbacks wire ``log_agent_invocation`` per ``.claude/rules/logging.md`` §4
  (mandatory duration + token attribution). State uses the ``temp:`` prefix so
  stopwatch keys never leak into persisted session state (agents.md §2).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from google.adk.agents import LlmAgent

from supply_chain_triage.utils.logging import log_agent_invocation

if TYPE_CHECKING:
    from google.adk.agents.callback_context import CallbackContext
    from google.adk.models.llm_response import LlmResponse

_AGENT_NAME = "hello_world"
_MODEL = "gemini-2.5-flash"
_INSTRUCTION = (Path(__file__).parent / "prompts" / "hello_world.md").read_text(
    encoding="utf-8",
)

# Keys scoped to this agent to avoid collisions when future agents (Classifier,
# Impact) add their own timers in a SequentialAgent pipeline.
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
        model=_MODEL,
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

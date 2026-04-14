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
"""

from __future__ import annotations

from pathlib import Path

from google.adk.agents import LlmAgent

_INSTRUCTION = (Path(__file__).parent / "prompts" / "hello_world.md").read_text(
    encoding="utf-8",
)

root_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="hello_world",
    description=(
        "Baseline greeter agent. Smoke-tests the ADK toolchain end-to-end. "
        "Has no tools and no data access."
    ),
    instruction=_INSTRUCTION,
)

"""Framework-portability shim for agent execution.

Per ADR-001 ("Agent Framework — Google ADK"), this module is **mandatory**:
it insulates the rest of the codebase from ADK-specific runner semantics so
that swapping to LangGraph / CrewAI / PydanticAI later is a ~20% rewrite
rather than ~80%. ADK imports are allowed here (this file is in ``runners/``).

Sprint 0 scope: define the ``AgentRunner`` protocol + a minimal ADK-backed
implementation that ``adk web`` and the FastAPI app factory can call. The
contract is deliberately narrow — ``run(agent, input_text, session_id?) -> str``.
Sprint 3 extends it when the Coordinator streams SSE events via the same seam.

The shim deliberately does not expose ADK's ``Session``, ``Runner``, or
``InvocationContext`` types in its public signatures — callers see plain
Python / Pydantic types only. Swapping frameworks rewrites this module's
implementation but keeps the public shape.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from google.adk.agents import LlmAgent


class AgentRunner(Protocol):
    """Framework-neutral interface for running an agent end-to-end.

    Implementations wrap a concrete framework's runner machinery. The public
    surface is intentionally narrow — Sprint 3 may extend with streaming /
    session methods but only via additions (never breaking changes).
    """

    async def run(
        self,
        agent: LlmAgent,
        input_text: str,
        session_id: str | None = None,
    ) -> str:
        """Execute an agent and return its final text response.

        Args:
            agent: The agent to invoke.
            input_text: User-provided text turn.
            session_id: Optional session identifier for multi-turn continuity.
                When ``None``, the implementation creates a transient session.

        Returns:
            The agent's final response text.
        """
        ...


class AdkAgentRunner:
    """ADK-backed :class:`AgentRunner`. Sprint 0 minimal implementation.

    Sprint 3 extends this to handle streaming (``Runner.run_async`` + SSE
    emission) and cross-agent state handoff through ADK sessions. For Sprint
    0, the shim just satisfies the protocol so ``adk web`` + the FastAPI
    smoke test have a callable seam.

    The ADK-specific Runner/SessionService wiring happens inside ``run`` to
    keep construction fast (no framework init on import).
    """

    async def run(
        self,
        agent: LlmAgent,
        input_text: str,
        session_id: str | None = None,
    ) -> str:
        """Run the agent end-to-end and return the final text response.

        Sprint 3 wires this through ``google.adk.runners.Runner`` +
        ``InMemorySessionService``. Sprint 0 raises ``NotImplementedError``
        pointing at Sprint 3 so callers get a loud failure if they reach
        the runner prematurely.
        """
        raise NotImplementedError(
            "sprint-3: AdkAgentRunner.run wires google.adk.runners.Runner "
            "with SessionService. Sprint 0 ships the shim only; adk web "
            "exercises the agent directly."
        )

"""Smoke tests for the hello_world baseline agent (test-plan §5.1)."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import structlog

from supply_chain_triage.modules.triage.agents.hello_world import agent as hw
from supply_chain_triage.modules.triage.agents.hello_world.agent import root_agent


class TestHelloWorldAgentDefinition:
    """Unit-level checks — no Gemini calls."""

    def test_agent_name_is_hello_world(self) -> None:
        assert root_agent.name == "hello_world"

    def test_agent_model_is_gemini_25_flash(self) -> None:
        # ADR-001 pins gemini-2.5-flash for Tier 1. Changing this needs an ADR.
        assert root_agent.model == "gemini-2.5-flash"

    def test_agent_has_instruction(self) -> None:
        # Instruction is loaded from prompts/hello_world.md at import time.
        instruction = root_agent.instruction
        assert isinstance(instruction, str)
        assert "greeter" in instruction.lower()
        # Rule check: the prompt mentions the "2 sentences" brevity budget.
        assert "2 sentences" in instruction

    def test_agent_has_logging_callbacks_wired(self) -> None:
        # logging.md §4 mandates log_agent_invocation — enforced via callbacks.
        assert root_agent.before_agent_callback is not None
        assert root_agent.after_model_callback is not None
        assert root_agent.after_agent_callback is not None


class TestHelloWorldCallbacks:
    """Telemetry callbacks — mock CallbackContext, assert state + log events."""

    def _ctx(self) -> MagicMock:
        ctx = MagicMock()
        ctx.state = {}
        return ctx

    def test_before_agent_stamps_start_time(self) -> None:
        ctx = self._ctx()
        hw._before_agent(ctx)
        key = f"temp:{hw._AGENT_NAME}:start_perf_ns"
        assert key in ctx.state
        assert isinstance(ctx.state[key], int)
        assert ctx.state[key] > 0

    def test_after_model_captures_usage_metadata(self) -> None:
        ctx = self._ctx()
        llm_response = SimpleNamespace(
            usage_metadata=SimpleNamespace(prompt_token_count=42, candidates_token_count=7)
        )
        hw._after_model(ctx, llm_response)  # type: ignore[arg-type]
        assert ctx.state[f"temp:{hw._AGENT_NAME}:tokens_in"] == 42
        assert ctx.state[f"temp:{hw._AGENT_NAME}:tokens_out"] == 7

    def test_after_model_degrades_when_metadata_missing(self) -> None:
        # Cached / retried responses may omit usage_metadata. Must not crash.
        ctx = self._ctx()
        llm_response = SimpleNamespace()
        hw._after_model(ctx, llm_response)  # type: ignore[arg-type]
        assert ctx.state[f"temp:{hw._AGENT_NAME}:tokens_in"] == 0
        assert ctx.state[f"temp:{hw._AGENT_NAME}:tokens_out"] == 0

    def test_after_agent_emits_agent_invoked_event(self) -> None:
        # Force project's structlog setup to run first, then override with
        # LogCapture so log_agent_invocation's events land in `capture.entries`.
        from supply_chain_triage.utils.logging import _configure_once, get_logger

        _configure_once()
        get_logger("agents")  # ensure the namespaced logger is registered
        capture = structlog.testing.LogCapture()
        structlog.configure(processors=[capture])
        try:
            ctx = self._ctx()
            hw._before_agent(ctx)
            hw._after_model(
                ctx,
                SimpleNamespace(
                    usage_metadata=SimpleNamespace(
                        prompt_token_count=100, candidates_token_count=25
                    )
                ),  # type: ignore[arg-type]
            )
            hw._after_agent(ctx)
        finally:
            structlog.reset_defaults()

        events = [e for e in capture.entries if e.get("event") == "agent_invoked"]
        assert len(events) == 1
        event = events[0]
        assert event["agent_name"] == "hello_world"
        assert event["model"] == "gemini-2.5-flash"
        assert event["tokens_in"] == 100
        assert event["tokens_out"] == 25
        assert isinstance(event["duration_ms"], float)
        assert event["duration_ms"] >= 0.0


class TestHelloWorldAgentIntegration:
    """Real Gemini round-trip (Test 5.1). Marked integration; skipped without key."""

    @pytest.mark.integration
    @pytest.mark.skipif(
        not os.environ.get("GEMINI_API_KEY") and not os.environ.get("SCT_SECRET__GEMINI_API_KEY"),
        reason="requires GEMINI_API_KEY for live Gemini call",
    )
    async def test_agent_responds_to_greeting(self) -> None:
        # Deferred: the real adk evaluator harness lands in Sprint 3 when the
        # runner wiring exists. Sprint 0's gate (§17 item #3) exercises this
        # via `adk web` interactively. This test is the automated counterpart
        # and currently skips unless GEMINI_API_KEY is set.
        pytest.skip(
            "Sprint 0: smoke covered by `adk web` manual check; "
            "automated via Sprint 3 runner wiring."
        )

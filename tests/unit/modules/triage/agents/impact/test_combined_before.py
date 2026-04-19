"""Unit tests for _make_combined_before composition in the impact agent.

The combined_before callable wraps an upstream rule check with the existing
timing stamp. On skip (rule returns Content), timing is NOT stamped — no
point timing an agent that won't run. On pass (rule returns None), timing
IS stamped and the agent proceeds normally.

Guards against regressions where a refactor drops the timing fallthrough.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

os.environ.setdefault("GCP_PROJECT_ID", "sct-test")
os.environ.setdefault("FIREBASE_PROJECT_ID", "sct-test")
os.environ.setdefault("SCT_DISABLE_SECRET_MANAGER", "1")

from google.genai import types as genai_types

from supply_chain_triage.modules.triage.agents.impact.agent import _make_combined_before

_TIMING_STATE_KEY = "temp:impact:start_perf_ns"


def _ctx() -> MagicMock:
    """Build a minimal CallbackContext mock with a real dict for state."""
    ctx = MagicMock()
    ctx.state = {}
    return ctx


def _skip_content() -> genai_types.Content:
    return genai_types.Content(
        role="model",
        parts=[genai_types.Part(text="rule-triggered skip")],
    )


class TestCombinedBefore:
    """Composition of upstream rule check + timing stamp on the impact agent."""

    def test_skips_timing_when_rule_returns_content(self) -> None:
        """Rule returns Content → combined returns same Content; timing NOT stamped."""
        skip = _skip_content()

        def _rule_check(_: MagicMock) -> genai_types.Content:
            return skip

        combined = _make_combined_before(_rule_check)
        ctx = _ctx()
        result = combined(ctx)

        assert result is skip
        assert _TIMING_STATE_KEY not in ctx.state

    def test_runs_timing_when_rule_returns_none(self) -> None:
        """Rule returns None → combined returns None; timing IS stamped."""

        def _rule_check(_: MagicMock) -> None:
            return None

        combined = _make_combined_before(_rule_check)
        ctx = _ctx()
        result = combined(ctx)

        assert result is None
        assert _TIMING_STATE_KEY in ctx.state
        assert isinstance(ctx.state[_TIMING_STATE_KEY], int)

"""Unit tests for create_triage_pipeline — U-11 through U-13.

Verifies the assembly shape, not ADK runtime behavior. Runtime behavior is
covered by the integration test (``tests/integration/test_triage_pipeline.py``).
"""

from __future__ import annotations

import os

os.environ.setdefault("GCP_PROJECT_ID", "sct-test")
os.environ.setdefault("FIREBASE_PROJECT_ID", "sct-test")
os.environ.setdefault("SCT_DISABLE_SECRET_MANAGER", "1")

from google.adk.agents import SequentialAgent

from supply_chain_triage.modules.triage.pipeline import create_triage_pipeline
from supply_chain_triage.modules.triage.pipeline.callbacks import _rule_b_safety_check


class TestCreateTriagePipeline:
    """U-11..U-13: shape-level assertions on the assembled pipeline."""

    def test_u11_returns_sequential_agent_named_triage_pipeline(self) -> None:
        pipeline = create_triage_pipeline()
        assert isinstance(pipeline, SequentialAgent)
        assert pipeline.name == "triage_pipeline"

    def test_u12_sub_agents_order_classifier_then_impact(self) -> None:
        pipeline = create_triage_pipeline()
        names = [sub.name for sub in pipeline.sub_agents]
        assert names == ["classifier", "impact"]

    def test_u13_before_agent_callback_is_rule_b(self) -> None:
        pipeline = create_triage_pipeline()
        callback = pipeline.before_agent_callback
        # ADK wraps callback configs into a list[Callable] — unwrap if needed.
        if isinstance(callback, list):
            assert _rule_b_safety_check in callback
        else:
            assert callback is _rule_b_safety_check

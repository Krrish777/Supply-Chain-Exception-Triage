"""Triage pipeline — SequentialAgent factory wiring classifier + impact with rule callbacks.

Rule B (safety override) is attached at pipeline level via ``before_agent_callback``.
Rule C/F (impact gate) is injected into the impact sub-agent via ``create_impact``.
Priority: B > C > F.
"""

from __future__ import annotations

from google.adk.agents import SequentialAgent

from supply_chain_triage.modules.triage.agents.classifier.agent import create_classifier
from supply_chain_triage.modules.triage.agents.impact.agent import create_impact
from supply_chain_triage.modules.triage.pipeline.callbacks import (
    _rule_b_safety_check,
    _rule_cf_skip_check,
)

_PIPELINE_NAME = "triage_pipeline"
_PIPELINE_DESCRIPTION = (
    "End-to-end triage pipeline: classifies the exception then (conditionally) "
    "assesses business impact. Rule B short-circuits the entire pipeline on "
    "safety keywords; Rule C/F gates the impact sub-agent."
)


def create_triage_pipeline() -> SequentialAgent:
    """Create the full triage SequentialAgent with Rule B + Rule C/F callbacks wired in."""
    classifier = create_classifier()
    impact = create_impact(before_agent_callback=_rule_cf_skip_check)
    return SequentialAgent(
        name=_PIPELINE_NAME,
        description=_PIPELINE_DESCRIPTION,
        before_agent_callback=_rule_b_safety_check,
        sub_agents=[classifier, impact],
    )


# ADK discovery — `adk web src/.../modules/triage/pipeline` looks for `root_agent`.
root_agent = create_triage_pipeline()

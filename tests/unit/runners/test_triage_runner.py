"""Unit tests for run_triage — U-14 through U-18.

Strategy: patch ``Runner.run_async`` to no-op and ``InMemorySessionService.get_session``
to return a SimpleNamespace whose ``state`` is a per-test fixture dict. This tests
the assembly logic (TriageResult construction from state) without touching ADK
runtime or Gemini.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from typing import Any

os.environ.setdefault("GCP_PROJECT_ID", "sct-test")
os.environ.setdefault("FIREBASE_PROJECT_ID", "sct-test")
os.environ.setdefault("SCT_DISABLE_SECRET_MANAGER", "1")

import pytest
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from supply_chain_triage.modules.triage.models.common_types import TriageStatus
from supply_chain_triage.runners.triage_runner import run_triage


def _classification_json(
    *,
    exception_type: str = "carrier_capacity_failure",
    severity: str = "HIGH",
    requires_human_approval: bool = False,
) -> str:
    return json.dumps(
        {
            "exception_type": exception_type,
            "subtype": "driver_shortage",
            "severity": severity,
            "confidence": 0.9,
            "key_facts": [],
            "reasoning": "fixture reasoning",
            "requires_human_approval": requires_human_approval,
            "safety_escalation": None,
        }
    )


def _impact_json(*, event_id: str = "EVT-TEST") -> str:
    return json.dumps(
        {
            "event_id": event_id,
            "affected_shipments": [],
            "total_value_at_risk_inr": 0,
            "total_penalty_exposure_inr": 0,
            "estimated_churn_impact_inr": None,
            "critical_path_shipment_id": None,
            "recommended_priority_order": [],
            "priority_reasoning": "",
            "has_reputation_risks": False,
            "reputation_risk_shipments": [],
            "total_financial_exposure_inr": 0,
            "cascade_risk_summary": "",
            "hub_congestion_risk": None,
            "estimated_delay_hours": 0.0,
            "summary": "",
        }
    )


@pytest.fixture
def fake_runner_state(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Patch Runner.run_async + get_session so tests control post-run state."""
    state: dict[str, Any] = {}

    async def _noop_run_async(*_args: Any, **_kwargs: Any) -> Any:
        if False:  # pragma: no cover — makes this an async generator
            yield

    async def _get_session(
        _self: Any, *, app_name: str, user_id: str, session_id: str
    ) -> SimpleNamespace:
        del app_name, user_id
        return SimpleNamespace(id=session_id, state=state)

    monkeypatch.setattr(Runner, "run_async", _noop_run_async)
    monkeypatch.setattr(InMemorySessionService, "get_session", _get_session)
    return state


class TestRunTriageAssembly:
    """U-14..U-18: runner assembles TriageResult correctly from post-run state."""

    async def test_u14_normal_path_complete(self, fake_runner_state: dict[str, Any]) -> None:
        fake_runner_state["triage:classification"] = _classification_json()
        fake_runner_state["triage:impact"] = _impact_json(event_id="EVT-001")

        result = await run_triage(event_id="EVT-001", raw_text="Driver cancelled.")

        assert result.status == TriageStatus.complete
        assert result.classification is not None
        assert result.classification.exception_type == "carrier_capacity_failure"
        assert result.impact is not None
        assert result.errors == []

    async def test_u15_rule_b_path_escalated_to_human_safety(
        self, fake_runner_state: dict[str, Any]
    ) -> None:
        fake_runner_state["triage:classification"] = _classification_json(
            exception_type="safety_incident", severity="CRITICAL"
        )
        fake_runner_state["triage:status"] = "escalated_to_human_safety"
        fake_runner_state["triage:skip_impact"] = True
        fake_runner_state["triage:rule_b_applied"] = True
        fake_runner_state["triage:escalation_priority"] = "safety"

        result = await run_triage(event_id="EVT-SAFETY", raw_text="Fire in cargo hold.")

        assert result.status == TriageStatus.escalated_to_human_safety
        assert result.impact is None
        assert result.escalation_priority is not None
        assert result.escalation_priority.value == "safety"
        assert "safety escalation" in result.summary.lower()

    async def test_u16_rule_f_path_low_severity_impact_skipped(
        self, fake_runner_state: dict[str, Any]
    ) -> None:
        fake_runner_state["triage:classification"] = _classification_json(severity="LOW")
        fake_runner_state["triage:status"] = "complete"
        fake_runner_state["triage:rule_f_applied"] = True
        # No triage:impact key — Rule F skipped it.

        result = await run_triage(event_id="EVT-LOW", raw_text="Routine minor delay.")

        assert result.status == TriageStatus.complete
        assert result.impact is None
        assert "Rule F" in result.summary

    async def test_u17_impact_parse_error_flips_to_partial(
        self, fake_runner_state: dict[str, Any]
    ) -> None:
        fake_runner_state["triage:classification"] = _classification_json()
        fake_runner_state["triage:impact"] = "{ this is not valid json"

        result = await run_triage(event_id="EVT-BAD", raw_text="Carrier missed pickup.")

        assert result.status == TriageStatus.partial
        assert result.impact is None
        assert any("impact_parse_error" in err for err in result.errors)

    async def test_u18_processing_time_ms_nonnegative(
        self, fake_runner_state: dict[str, Any]
    ) -> None:
        fake_runner_state["triage:classification"] = _classification_json()
        fake_runner_state["triage:impact"] = _impact_json()

        result = await run_triage(event_id="EVT-TIME", raw_text="Test event.")

        assert result.processing_time_ms >= 0

    async def test_requires_human_approval_flips_to_escalated(
        self, fake_runner_state: dict[str, Any]
    ) -> None:
        """Bonus: low-confidence classifications escalate automatically."""
        fake_runner_state["triage:classification"] = _classification_json(
            requires_human_approval=True
        )
        fake_runner_state["triage:impact"] = _impact_json()

        result = await run_triage(event_id="EVT-LOWCONF", raw_text="Ambiguous text.")

        assert result.status == TriageStatus.escalated_to_human

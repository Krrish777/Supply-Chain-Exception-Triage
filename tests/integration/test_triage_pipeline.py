"""Integration test I-1 — full NH-48-style triage pipeline end-to-end.

Seeds the Firestore emulator with a truck-breakdown exception + company
context, then runs the complete pipeline (classifier + impact, Rule B/C/F
callbacks, deterministic post-classification overrides) against the real
Gemini API. Asserts the assembled ``TriageResult`` has the expected shape.

Gated requirements:
    - Firestore emulator running on localhost:8080 (``require_firestore_emulator``).
    - ``GEMINI_API_KEY`` in env — skipped otherwise.
    - Marker ``@pytest.mark.integration`` — excluded from ``pytest -m "not integration"``.

Cost: one classifier run + one impact run \u2248 a few thousand Gemini tokens.
Run manually during Sprint 3 Day 3 validation; not part of the pre-commit loop.
"""

from __future__ import annotations

import os

os.environ.setdefault("GCP_PROJECT_ID", "sct-test")
os.environ.setdefault("FIREBASE_PROJECT_ID", "sct-test")
os.environ.setdefault("SCT_DISABLE_SECRET_MANAGER", "1")

import pytest
from google.cloud.firestore import AsyncClient

from supply_chain_triage.modules.triage.models.common_types import TriageStatus
from supply_chain_triage.runners.triage_runner import run_triage

pytestmark = pytest.mark.integration

_PROJECT_ID = "sct-test"
_EVENT_ID = "EXC-TEST-PIPELINE-I1"
_COMPANY_ID = "swiftlogix-test-i1"

_RAW_TEXT = (
    "BlueDart truck BD-MH12-4521 broke down on the Mumbai-Pune Expressway "
    "near Lonavala at 06:30 IST. Driver reports engine failure. 12 packages "
    "onboard for delivery today including 3 high-value B2B shipments for "
    "MegaMart. Mechanic ETA 3 hours. No injuries reported."
)


@pytest.fixture
async def seeded_exception(
    require_firestore_emulator: None,  # fixture guard — value unused
) -> None:
    """Seed a truck-breakdown exception + company profile into the emulator."""
    db = AsyncClient(project=_PROJECT_ID)

    await (
        db.collection("companies")
        .document(_COMPANY_ID)
        .set(
            {
                "company_id": _COMPANY_ID,
                "name": "SwiftLogix Test I1",
                "profile_summary": (
                    "Small 3PL operator based in Mumbai, serving the Mumbai-Gujarat-Chennai "
                    "corridor. Specializes in FMCG and pharmaceutical distribution."
                ),
                "num_trucks": 15,
                "num_employees": 42,
                "regions_of_operation": ["Mumbai", "Pune", "Gujarat"],
                "carriers": ["BlueDart", "Delhivery"],
                "customer_portfolio": {
                    "d2c_percentage": 0.30,
                    "b2b_percentage": 0.45,
                    "b2b_enterprise_percentage": 0.25,
                    "top_customers": ["MegaMart India", "PharmaCo"],
                },
                "avg_daily_revenue_inr": 800000,
                "active": True,
            }
        )
    )
    await (
        db.collection("exceptions")
        .document(_EVENT_ID)
        .set(
            {
                "event_id": _EVENT_ID,
                "timestamp": "2026-04-19T06:30:00+00:00",
                "source_channel": "manual_entry",
                "sender": {"name": "Dispatch Control", "role": "operations"},
                "raw_content": _RAW_TEXT,
                "original_language": None,
                "english_translation": None,
                "media_urls": [],
                "metadata": {"company_id": _COMPANY_ID},
            }
        )
    )

    yield

    await db.collection("companies").document(_COMPANY_ID).delete()
    await db.collection("exceptions").document(_EVENT_ID).delete()


@pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY"),
    reason="GEMINI_API_KEY required for live pipeline integration test",
)
async def test_i1_full_pipeline_returns_structured_triage_result(
    seeded_exception: None,  # fixture seeds + cleans up — value unused
) -> None:
    """Full pipeline runs end-to-end and returns a valid TriageResult."""
    result = await run_triage(event_id=_EVENT_ID, raw_text=_RAW_TEXT)

    assert result.event_id == _EVENT_ID
    assert result.status in {
        TriageStatus.complete,
        TriageStatus.escalated_to_human,
        TriageStatus.partial,
    }
    assert result.classification is not None
    assert result.classification.severity in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    assert result.processing_time_ms >= 0
    assert len(result.summary) > 0


# ---------------------------------------------------------------------------
# I-2 — Rule B short-circuit
# ---------------------------------------------------------------------------

_EVENT_ID_I2 = "EXC-TEST-RULE-B-I2"
_SAFETY_RAW_TEXT = "Tanker explosion on NH-48. Driver injured near km 72."


async def test_i2_rule_b_short_circuits_pipeline() -> None:
    """Rule B fires on safety keywords; pipeline short-circuits before classifier.

    Rule B is deterministic keyword-matching that runs on the pipeline's
    ``before_agent_callback`` — it fires BEFORE the classifier sub-agent, which
    means no Gemini call and no Firestore read happen. The test runs cheap even
    in CI. The placeholder ClassificationResult written by Rule B surfaces as a
    structured ``TriageResult`` with ``escalated_to_human_safety`` status.
    """
    result = await run_triage(event_id=_EVENT_ID_I2, raw_text=_SAFETY_RAW_TEXT)

    assert result.event_id == _EVENT_ID_I2
    assert result.status == TriageStatus.escalated_to_human_safety
    assert result.impact is None
    assert result.escalation_priority is not None
    assert result.escalation_priority.value == "safety"
    assert "safety" in result.summary.lower()

    # Rule B writes a placeholder ClassificationResult to state — verify it parses
    # and has the expected shape.
    assert result.classification is not None
    assert result.classification.exception_type == "safety_incident"
    assert result.classification.severity == "CRITICAL"
    assert result.classification.requires_human_approval is True

"""Firestore emulator integration test (test-plan §6.1).

Round-trips a ``CompanyProfile`` document through the running Firestore
emulator. Skips gracefully if the emulator isn't running — see
``tests/conftest.py::require_firestore_emulator``.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


async def test_write_and_read_company_profile_round_trip(
    require_firestore_emulator: None,
) -> None:
    # Deferred import — triggers firestore client init, which must happen
    # after conftest's _set_emulator_env session fixture.
    from google.cloud import firestore

    from supply_chain_triage.modules.triage.models.company_profile import CompanyProfile

    # Given: a valid CompanyProfile
    profile = CompanyProfile.model_validate(
        {
            "company_id": "test_co_001",
            "name": "NimbleFreight (test)",
            "profile_summary": "Emulator round-trip fixture",
            "num_trucks": 22,
            "num_employees": 35,
            "regions_of_operation": ["Maharashtra"],
            "carriers": ["Delhivery"],
            "customer_portfolio": {
                "d2c_percentage": 0.3,
                "b2b_percentage": 0.6,
                "b2b_enterprise_percentage": 0.1,
                "top_customers": ["Trina Logistics"],
            },
            "avg_daily_revenue_inr": 180_000,
            "active": True,
        }
    )

    client = firestore.AsyncClient(project="sct-test")
    doc_ref = client.collection("companies").document(profile.company_id)

    try:
        # When: write then read back
        await doc_ref.set(profile.model_dump(mode="json"))
        snapshot = await doc_ref.get()
        assert snapshot.exists, "Firestore emulator did not persist the write"
        read_back = CompanyProfile.model_validate(snapshot.to_dict())

        # Then: round-tripped doc equals original
        assert read_back == profile
    finally:
        # Per-test teardown — delete the doc so the emulator stays clean.
        await doc_ref.delete()

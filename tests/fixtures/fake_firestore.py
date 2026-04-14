"""In-process Firestore fake backed by ``mockfirestore``.

For unit tests of pure tool logic only — per ``.claude/rules/testing.md`` §5:
``mockfirestore`` does NOT emulate transactions, indexes, or security rules
accurately. Integration tests (``tests/integration/``) talk to the real
Firestore emulator via the session-scoped fixture in ``tests/conftest.py``.

Sprint 0 ships the factory. Sprint 1+ seeds it per-test with realistic data.
"""

from __future__ import annotations

from typing import Any

from mockfirestore import MockFirestore  # type: ignore[import-untyped]


def make_fake_firestore() -> MockFirestore:
    """Return a fresh in-memory Firestore client.

    Call per test (or per test class) to guarantee isolation — mockfirestore
    instances carry state across calls otherwise. For session-scoped sharing,
    reset via ``client.reset()`` between tests.
    """
    return MockFirestore()


def seed_company(
    client: MockFirestore,
    company_id: str,
    *,
    extra: dict[str, Any] | None = None,
) -> None:
    """Seed a minimal company doc for tests that need one.

    Sprint 1+ extensions grow this helper with ``seed_shipment`` /
    ``seed_customer`` / ``seed_exception`` for specific scenarios.
    """
    doc = {
        "company_id": company_id,
        "name": f"Test Company {company_id}",
        "profile_summary": "(seeded)",
        "num_trucks": 10,
        "num_employees": 15,
        "regions_of_operation": ["Maharashtra"],
        "carriers": ["Delhivery"],
        "customer_portfolio": {
            "d2c_percentage": 0.5,
            "b2b_percentage": 0.4,
            "b2b_enterprise_percentage": 0.1,
            "top_customers": [],
        },
        "avg_daily_revenue_inr": 100_000,
        "active": True,
    }
    if extra:
        doc.update(extra)
    client.collection("companies").document(company_id).set(doc)

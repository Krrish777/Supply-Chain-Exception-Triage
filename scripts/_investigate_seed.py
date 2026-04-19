"""One-off diagnostic: act as the agent against the live emulator.

Mirrors `modules/triage/agents/impact/tools.py::get_affected_shipments`
exactly — same collection, same two-filter query — then simulates each
test prompt from the eval plan and reports hit/miss.

Run with: uv run python scripts/_investigate_seed.py
"""

from __future__ import annotations

import asyncio
import os
from collections import Counter
from typing import Any

os.environ["FIRESTORE_EMULATOR_HOST"] = "localhost:8080"

from google.cloud.firestore import AsyncClient
from google.cloud.firestore_v1.base_query import FieldFilter

PROJECT_ID = "demo-no-project"
SHIPMENTS = "shipments"


async def dump_fixture_reality(db: AsyncClient) -> dict[str, Any]:
    """Inventory what's actually in the emulator right now."""
    report: dict[str, Any] = {}

    # Per-collection counts.
    for coll in ["companies", "exceptions", "customers", "routes", "hubs", "shipments"]:
        docs = [d async for d in db.collection(coll).stream()]
        report[coll] = len(docs)

    # Shipments deep-dive — the fields get_affected_shipments filters on.
    ships = [d.to_dict() async for d in db.collection(SHIPMENTS).stream()]
    report["shipments_status"] = dict(Counter(s.get("status") for s in ships))
    report["shipments_region"] = dict(Counter(s.get("region") for s in ships))
    report["shipments_vehicle_id"] = sorted(
        {s.get("vehicle_id") for s in ships if s.get("vehicle_id")}
    )
    report["shipments_route_id"] = sorted({s.get("route_id") for s in ships if s.get("route_id")})
    report["shipments_origin"] = sorted({s.get("origin") for s in ships if s.get("origin")})
    report["shipments_destination"] = sorted(
        {s.get("destination") for s in ships if s.get("destination")}
    )
    report["shipments_customer_ids"] = sorted(
        {s.get("customer_id") for s in ships if s.get("customer_id")}
    )
    report["shipments_company_ids"] = sorted(
        {s.get("company_id") for s in ships if s.get("company_id")}
    )

    # Hub cities (what the LLM would name when asked "affected hub")
    hubs = [d.to_dict() async for d in db.collection("hubs").stream()]
    report["hub_ids"] = sorted({h.get("hub_id") for h in hubs if h.get("hub_id")})
    report["hub_cities"] = sorted({h.get("city") for h in hubs if h.get("city")})

    # Routes
    routes = [d.to_dict() async for d in db.collection("routes").stream()]
    report["route_ids"] = sorted({r.get("route_id") for r in routes if r.get("route_id")})

    # Companies
    comps = [d.to_dict() async for d in db.collection("companies").stream()]
    report["company_ids"] = sorted({c.get("company_id") for c in comps if c.get("company_id")})

    # Exception event_ids
    excs = [d.to_dict() async for d in db.collection("exceptions").stream()]
    report["exception_event_ids"] = sorted({e.get("event_id") for e in excs if e.get("event_id")})
    report["exception_metadata_company_ids"] = sorted(
        {e.get("metadata", {}).get("company_id") for e in excs if e.get("metadata")}
    )

    return report


async def simulate_query(
    db: AsyncClient, scope_type: str, scope_value: str
) -> tuple[int, list[str]]:
    """Exactly mirror get_affected_shipments()."""
    allowed = {"vehicle_id", "route_id", "region"}
    if scope_type not in allowed:
        return (-1, [f"INVALID scope_type={scope_type!r} — tool would reject"])
    query = (
        db.collection(SHIPMENTS)
        .where(filter=FieldFilter("status", "==", "in_transit"))
        .where(filter=FieldFilter(scope_type, "==", scope_value))
    )
    docs = [d async for d in query.stream()]
    return len(docs), [d.id for d in docs]


# (prompt_id, label, likely_scope_type, likely_scope_value)
# Scope values chosen the way the classifier WOULD extract them from the raw_content,
# not normalized. This mirrors the real failure mode.
TEST_PROMPTS = [
    # A. Smoke tests — seeded fixtures
    ("A1", "Vehicle breakdown BD-MH12-4521", "vehicle_id", "BD-MH12-4521"),
    ("A2", "Nhava Sheva port flooding (region)", "region", "Nhava Sheva"),
    ("A2b", "Nhava Sheva port flooding (region=maharashtra)", "region", "maharashtra"),
    ("A3", "MegaMart order #MM-2026-8834 escalation", "vehicle_id", "MM-2026-8834"),
    ("A4", "Vapi NH8 chemical spill (region=gujarat)", "region", "gujarat"),
    ("A4b", "Vapi NH8 chemical spill (region=Vapi)", "region", "Vapi"),
    ("A5", "Chennai port customs hold CHN-2026-442", "region", "Chennai"),
    # B. Category coverage
    ("B6", "Kandla cyclone (region=gujarat)", "region", "gujarat"),
    ("B6b", "Kandla cyclone (region=Kandla)", "region", "Kandla"),
    ("B7", "Truckers strike nationwide", "region", "nationwide"),
    ("B8", "WMS Bhiwandi DC ransomware (USER'S ACTUAL TEST)", "region", "Bhiwandi DC"),
    ("B8b", "WMS Bhiwandi DC (region=maharashtra)", "region", "maharashtra"),
    ("B9", "MegaMart Hyderabad DC rejection", "region", "Hyderabad"),
    ("B10", "E-way bill Hosur RTO", "region", "Hosur"),
    # C. Multilingual
    ("C11", "Hindi: Truck MH-04-AB-1234 Nasik-Dhule", "vehicle_id", "MH-04-AB-1234"),
    ("C12", "Hinglish: Truck TN-09-BX-5521 Chennai bypass", "vehicle_id", "TN-09-BX-5521"),
    ("C13", "Tamil: Coimbatore warehouse power outage", "region", "Coimbatore"),
    ("C14", "Code-switch: Panvel toll jam", "region", "Panvel"),
    # D. Adversarial
    ("D15", "'Truck late.' (thin signal)", "vehicle_id", "unknown"),
    ("D17", "Mixed events split-test", "vehicle_id", "BD-MH12-4521"),
    # E. Impact stress
    ("E21", "High fan-out customer (Milan Electronics?)", "region", "karnataka"),
]


async def main() -> None:
    db = AsyncClient(project=PROJECT_ID)

    print("=" * 80)
    print("PHASE 1: FIXTURE REALITY — what's actually seeded")
    print("=" * 80)
    reality = await dump_fixture_reality(db)
    for k, v in reality.items():
        print(f"\n{k}:")
        print(f"  {v}")

    print("\n\n" + "=" * 80)
    print("PHASE 2: SIMULATED EVAL RUN — hit/miss per prompt")
    print("=" * 80)
    print(f"{'ID':<5} {'SCOPE':<12} {'VALUE':<30} {'HITS':<6} {'RESULT'}")
    print("-" * 80)
    hit_count = 0
    miss_count = 0
    for pid, label, scope_t, scope_v in TEST_PROMPTS:
        count, ids = await simulate_query(db, scope_t, scope_v)
        if count == -1:
            status = "INVALID"
        elif count == 0:
            status = "MISS"
            miss_count += 1
        else:
            status = f"HIT ({ids[:3]}{'...' if len(ids) > 3 else ''})"
            hit_count += 1
        print(f"{pid:<5} {scope_t:<12} {scope_v[:29]:<30} {count:<6} {status}")

    print("\n" + "-" * 80)
    print(f"Summary: {hit_count} HIT  /  {miss_count} MISS  /  {len(TEST_PROMPTS)} total")


if __name__ == "__main__":
    asyncio.run(main())

"""Seed the Firestore emulator with ALL demo data (classifier + impact).

Bypasses the Settings layer — connects directly to the emulator.

Usage:
    uv run python scripts/seed_emulator.py
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

# Force emulator connection BEFORE any imports
os.environ["FIRESTORE_EMULATOR_HOST"] = "localhost:8080"

from google.cloud.firestore import AsyncClient

SEED_DIR = Path(__file__).parent / "seed"
PROJECT_ID = "demo-no-project"


async def main() -> None:
    """Seed all collections into the Firestore emulator."""
    db = AsyncClient(project=PROJECT_ID)

    # 1. Seed classifier data (inline — same as seed_classifier_demo.py)
    print("=== Seeding classifier data ===")

    company_swiftlogix = {
        "company_id": "swiftlogix-001",
        "name": "SwiftLogix Pvt. Ltd.",
        "profile_summary": (
            "Small 3PL operator based in Mumbai, serving the Mumbai-Gujarat-Chennai "
            "corridor. Specializes in FMCG and pharmaceutical distribution."
        ),
        "num_trucks": 15,
        "num_employees": 42,
        "regions_of_operation": ["Mumbai", "Pune", "Gujarat", "Chennai", "Bengaluru"],
        "carriers": ["BlueDart", "Delhivery", "DTDC", "Gati"],
        "customer_portfolio": {
            "d2c_percentage": 0.30,
            "b2b_percentage": 0.45,
            "b2b_enterprise_percentage": 0.25,
            "top_customers": ["MegaMart India", "PharmaCo", "FreshDaily"],
        },
        "avg_daily_revenue_inr": 800000,
        "active": True,
    }
    await db.collection("companies").document("swiftlogix-001").set(company_swiftlogix)
    print("  [OK] companies/swiftlogix-001")

    exceptions = [
        {
            "event_id": "EXC-2026-0001",
            "timestamp": "2026-04-16T06:30:00+00:00",
            "source_channel": "manual_entry",
            "sender": {"name": "Dispatch Control", "role": "operations"},
            "raw_content": (
                "BlueDart truck BD-MH12-4521 broke down on the Mumbai-Pune Expressway "
                "near Lonavala at 06:30 IST. Driver reports engine failure. 12 packages "
                "onboard for delivery today including 3 high-value B2B shipments for "
                "MegaMart. Mechanic ETA 3 hours. No injuries reported."
            ),
            "original_language": None,
            "english_translation": None,
            "media_urls": [],
            "metadata": {"company_id": "swiftlogix-001"},
        },
        {
            "event_id": "EXC-2026-0002",
            "timestamp": "2026-04-16T08:00:00+00:00",
            "source_channel": "manual_entry",
            "sender": {"name": "Port Liaison", "role": "operations"},
            "raw_content": (
                "URGENT: Heavy monsoon flooding in Nhava Sheva port area since last "
                "night. Multiple container yards waterlogged. Access roads to JNPT "
                "blocked. Port operations suspended until further notice."
            ),
            "original_language": None,
            "english_translation": None,
            "media_urls": [],
            "metadata": {"company_id": "swiftlogix-001"},
        },
    ]
    for exc in exceptions:
        await db.collection("exceptions").document(exc["event_id"]).set(exc)
        print(f"  [OK] exceptions/{exc['event_id']}")

    # 2. Seed impact data from JSON files
    print("\n=== Seeding impact data ===")

    seed_files = {
        "customers": "customers.json",
        "routes": "routes.json",
        "hubs": "hubs.json",
        "shipments": "shipments.json",
    }

    for collection_name, filename in seed_files.items():
        filepath = SEED_DIR / filename
        if not filepath.exists():
            print(f"  [SKIP] {filename} not found")
            continue

        with filepath.open() as f:
            docs = json.load(f)

        # Determine the document ID field
        id_fields = {
            "customers": "customer_id",
            "routes": "route_id",
            "hubs": "hub_id",
            "shipments": "shipment_id",
        }
        id_field = id_fields[collection_name]

        for doc in docs:
            doc_id = doc[id_field]
            await db.collection(collection_name).document(doc_id).set(doc)
            print(f"  [OK] {collection_name}/{doc_id}")

        print(f"  --- {len(docs)} {collection_name} seeded")

    # 3. Seed NimbleFreight company
    nimble_path = SEED_DIR / "companies_nimblefreight.json"
    if nimble_path.exists():
        with nimble_path.open() as f:
            nimble = json.load(f)
        doc_id = nimble.get("company_id", "comp_nimblefreight")
        await db.collection("companies").document(doc_id).set(nimble)
        print(f"  [OK] companies/{doc_id}")

    # Summary
    print("\n=== Verification ===")
    for coll in ["companies", "exceptions", "customers", "routes", "hubs", "shipments"]:
        docs = [d async for d in db.collection(coll).stream()]
        print(f"  {coll}: {len(docs)} docs")

    print("\nDone! Check http://localhost:4000/firestore to verify.")


if __name__ == "__main__":
    asyncio.run(main())

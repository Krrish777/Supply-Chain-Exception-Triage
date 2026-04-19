"""Seed the Firestore emulator with ALL demo data (classifier + impact).

Loads every fixture from ``scripts/seed/*.json`` — single source of truth
for both the classifier and impact demos. Bypasses the Settings layer and
connects directly to the emulator.

Usage:
    uv run python scripts/seed_emulator.py

Collections seeded:
    companies      — SwiftLogix (classifier + impact) + NimbleFreight (impact)
    exceptions     — EXC-2026-0001..0005 (all 5 demo scenarios)
    customers      — customer CRM profiles (impact)
    routes         — logistics corridors (impact)
    hubs           — hub/facility nodes (impact)
    shipments      — active + delivered shipments (impact)
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


async def _seed_docs(
    db: AsyncClient,
    collection: str,
    docs: list[dict],
    id_field: str,
) -> int:
    """Write a list of documents to a collection, keyed by ``id_field``."""
    for doc in docs:
        doc_id = doc[id_field]
        await db.collection(collection).document(doc_id).set(doc)
        print(f"  [OK] {collection}/{doc_id}")
    return len(docs)


def _load(filename: str) -> list[dict] | dict:
    """Load a JSON fixture from ``scripts/seed/``."""
    with (SEED_DIR / filename).open(encoding="utf-8") as fh:
        return json.load(fh)


def _as_list(data: list[dict] | dict) -> list[dict]:
    """Normalise single-object fixtures into a list."""
    if isinstance(data, dict):
        return [data]
    return data


async def main() -> None:
    """Seed all collections into the Firestore emulator."""
    db = AsyncClient(project=PROJECT_ID)

    # Companies — SwiftLogix (classifier + impact) and NimbleFreight (impact).
    print("=== Seeding companies ===")
    await _seed_docs(
        db,
        "companies",
        _as_list(_load("companies_swiftlogix.json")),
        id_field="company_id",
    )
    await _seed_docs(
        db,
        "companies",
        _as_list(_load("companies_nimblefreight.json")),
        id_field="company_id",
    )

    # Exceptions — all 5 demo scenarios.
    print("\n=== Seeding exceptions ===")
    await _seed_docs(
        db,
        "exceptions",
        _as_list(_load("exceptions.json")),
        id_field="event_id",
    )

    # Impact demo fixtures.
    print("\n=== Seeding impact data ===")
    impact_fixtures = {
        "customers": ("customers.json", "customer_id"),
        "routes": ("routes.json", "route_id"),
        "hubs": ("hubs.json", "hub_id"),
        "shipments": ("shipments.json", "shipment_id"),
    }
    for collection, (filename, id_field) in impact_fixtures.items():
        path = SEED_DIR / filename
        if not path.exists():
            print(f"  [SKIP] {filename} not found")
            continue
        count = await _seed_docs(
            db,
            collection,
            _as_list(_load(filename)),
            id_field=id_field,
        )
        print(f"  --- {count} {collection} seeded")

    # Summary.
    print("\n=== Verification ===")
    for coll in ["companies", "exceptions", "customers", "routes", "hubs", "shipments"]:
        docs = [d async for d in db.collection(coll).stream()]
        print(f"  {coll}: {len(docs)} docs")

    print("\nDone! Check http://localhost:4000/firestore to verify.")


if __name__ == "__main__":
    asyncio.run(main())

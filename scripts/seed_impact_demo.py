"""Seed Firestore with Impact agent demo data.

Loads customers, routes, hubs, shipments, and companies (NimbleFreight) from
``scripts/seed/`` JSON files and writes them to Firestore.

Usage::

    uv run python scripts/seed_impact_demo.py                       # dry-run
    uv run python scripts/seed_impact_demo.py --live                # write to emulator/prod
    uv run python scripts/seed_impact_demo.py --live --collection customers
    FIRESTORE_EMULATOR_HOST=localhost:8080 uv run python scripts/seed_impact_demo.py --live

Collections seeded:
    customers           — 7 customer CRM profiles (2 companies)
    routes              — 4 Indian logistics corridors
    hubs                — 8 hub/facility nodes
    shipments           — 25 shipments (active + delivered) across both companies
    companies           — NimbleFreight profile (SwiftLogix seeded by seed_classifier_demo.py)
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

SEED_DIR = Path(__file__).parent / "seed"

# Maps collection name → JSON file stem (relative to SEED_DIR)
_COLLECTIONS: dict[str, str] = {
    "customers": "customers",
    "routes": "routes",
    "hubs": "hubs",
    "shipments": "shipments",
    "companies": "companies_nimblefreight",
}

# Primary key field per collection (used as Firestore document ID)
_DOC_ID_FIELD: dict[str, str] = {
    "customers": "customer_id",
    "routes": "route_id",
    "hubs": "hub_id",
    "shipments": "shipment_id",
    "companies": "company_id",
}


def _load_json(file_stem: str) -> list[dict] | dict:
    """Load seed data from a JSON file in SEED_DIR."""
    path = SEED_DIR / f"{file_stem}.json"
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _as_list(data: list[dict] | dict) -> list[dict]:
    """Normalise single-object JSON files to a list."""
    if isinstance(data, dict):
        return [data]
    return data


def _dry_run(collections: list[str]) -> None:
    """Print a summary of what would be seeded without touching Firestore."""
    print("Dry-run mode — showing seed data summary")
    print("=" * 60)
    total = 0
    for collection in collections:
        file_stem = _COLLECTIONS[collection]
        path = SEED_DIR / f"{file_stem}.json"
        if not path.exists():
            print(f"  [MISSING] {collection:15s}  ({path})")
            continue
        try:
            docs = _as_list(_load_json(file_stem))
        except json.JSONDecodeError as exc:
            print(f"  [INVALID] {collection:15s}  ({exc})")
            continue
        id_field = _DOC_ID_FIELD[collection]
        ids = [d.get(id_field, "<no-id>") for d in docs]
        print(f"  [READY]   {collection:15s}  {len(docs)} docs: {ids}")
        total += len(docs)
    print(f"\nTotal: {total} documents across {len(collections)} collection(s).")


async def _seed_collection(db, collection: str) -> int:
    """Write all documents for one collection to Firestore.

    Returns count of documents written.
    """
    file_stem = _COLLECTIONS[collection]
    docs = _as_list(_load_json(file_stem))
    id_field = _DOC_ID_FIELD[collection]
    for doc in docs:
        doc_id = doc[id_field]
        await db.collection(collection).document(doc_id).set(doc)
        print(f"  [OK] {collection}/{doc_id}")
    return len(docs)


async def _seed_live(collections: list[str]) -> None:
    """Write seed data to Firestore (emulator or prod)."""
    import os

    os.environ.setdefault("GCP_PROJECT_ID", "supply-chain-triage-dev")
    os.environ.setdefault("FIREBASE_PROJECT_ID", "supply-chain-triage-dev")

    from supply_chain_triage.core.config import get_firestore_client

    db = get_firestore_client()
    totals: dict[str, int] = {}
    for collection in collections:
        print(f"\nSeeding {collection}...")
        totals[collection] = await _seed_collection(db, collection)

    print("\n" + "=" * 60)
    print("Seeding complete:")
    for collection, count in totals.items():
        print(f"  {collection:15s}  {count} docs")
    print(f"  {'TOTAL':15s}  {sum(totals.values())} docs")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Write to Firestore (emulator if FIRESTORE_EMULATOR_HOST set, else prod).",
    )
    parser.add_argument(
        "--collection",
        choices=list(_COLLECTIONS.keys()),
        default=None,
        help="Seed a single collection only (default: all).",
    )
    args = parser.parse_args()

    collections = [args.collection] if args.collection else list(_COLLECTIONS.keys())

    if args.live:
        print(f"Writing seed data to Firestore: {collections}")
        asyncio.run(_seed_live(collections))
    else:
        _dry_run(collections)


if __name__ == "__main__":
    main()

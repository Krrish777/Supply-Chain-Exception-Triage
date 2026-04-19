"""Seed Firestore with classifier demo data — 5 exception events + SwiftLogix.

Loads from ``scripts/seed/exceptions.json`` and
``scripts/seed/companies_swiftlogix.json`` so the classifier and impact
demos share a single source of truth (see also ``scripts/seed_emulator.py``
which seeds everything in one shot).

Usage:
    uv run python scripts/seed_classifier_demo.py                    # dry-run
    uv run python scripts/seed_classifier_demo.py --live             # write to emulator/prod
    FIRESTORE_EMULATOR_HOST=localhost:8080 uv run python scripts/seed_classifier_demo.py --live
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

SEED_DIR = Path(__file__).parent / "seed"


def _load(filename: str) -> list[dict] | dict:
    """Load a JSON fixture from ``scripts/seed/``."""
    with (SEED_DIR / filename).open(encoding="utf-8") as fh:
        return json.load(fh)


def _as_list(data: list[dict] | dict) -> list[dict]:
    """Normalise single-object fixtures into a list."""
    if isinstance(data, dict):
        return [data]
    return data


async def seed_live() -> None:
    """Write seed data to Firestore (emulator or prod)."""
    import os

    os.environ.setdefault("GCP_PROJECT_ID", "supply-chain-triage-dev")
    os.environ.setdefault("FIREBASE_PROJECT_ID", "supply-chain-triage-dev")

    from supply_chain_triage.core.config import get_firestore_client

    db = get_firestore_client()

    company = _load("companies_swiftlogix.json")
    assert isinstance(company, dict)
    await db.collection("companies").document(company["company_id"]).set(company)
    print(f"  [OK] companies/{company['company_id']}")

    exceptions = _as_list(_load("exceptions.json"))
    for exc in exceptions:
        await db.collection("exceptions").document(exc["event_id"]).set(exc)
        print(f"  [OK] exceptions/{exc['event_id']}")

    print(f"\nSeeded 1 company + {len(exceptions)} exceptions.")


def dry_run() -> None:
    """Print seed data without writing to Firestore."""
    company = _load("companies_swiftlogix.json")
    exceptions = _as_list(_load("exceptions.json"))
    assert isinstance(company, dict)

    print("Dry-run mode — showing seed data")
    print("=" * 60)
    print(f"\nCompany: {company['name']} ({company['company_id']})")
    print(
        f"  Trucks: {company['num_trucks']}, Revenue: Rs {company['avg_daily_revenue_inr']:,}/day"
    )
    print(f"\nExceptions ({len(exceptions)}):")
    for exc in exceptions:
        content_preview = exc["raw_content"][:80] + "..."
        print(f"  {exc['event_id']}: {content_preview}")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Write to Firestore")
    args = parser.parse_args()

    if args.live:
        print("Writing seed data to Firestore...")
        asyncio.run(seed_live())
    else:
        dry_run()


if __name__ == "__main__":
    main()

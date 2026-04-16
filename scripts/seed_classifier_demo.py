"""Seed Firestore with classifier demo data — 5 exception events + 1 company.

Usage:
    uv run python scripts/seed_classifier_demo.py                    # dry-run
    uv run python scripts/seed_classifier_demo.py --live             # write to emulator/prod
    FIRESTORE_EMULATOR_HOST=localhost:8080 uv run python scripts/seed_classifier_demo.py --live
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime

# Demo company profile — small 3PL in Mumbai.
COMPANY = {
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

# 5 exception events covering different types and severities.
EXCEPTIONS = [
    {
        "event_id": "EXC-2026-0001",
        "timestamp": datetime(2026, 4, 16, 6, 30, tzinfo=UTC).isoformat(),
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
        "timestamp": datetime(2026, 4, 16, 8, 0, tzinfo=UTC).isoformat(),
        "source_channel": "manual_entry",
        "sender": {"name": "Port Liaison", "role": "operations"},
        "raw_content": (
            "URGENT: Heavy monsoon flooding in Nhava Sheva port area since last "
            "night. Multiple container yards waterlogged. Access roads to JNPT "
            "blocked. Port operations suspended until further notice. Estimated "
            "200+ containers affected across all operators. Water level still "
            "rising. Met department predicts continued heavy rain for 48 hours."
        ),
        "original_language": None,
        "english_translation": None,
        "media_urls": [],
        "metadata": {"company_id": "swiftlogix-001"},
    },
    {
        "event_id": "EXC-2026-0003",
        "timestamp": datetime(2026, 4, 16, 10, 15, tzinfo=UTC).isoformat(),
        "source_channel": "manual_entry",
        "sender": {"name": "Rajesh Kumar", "role": "VP Operations, MegaMart India"},
        "raw_content": (
            "FINAL WARNING - This is our third escalation this month regarding "
            "delivery delays. Order #MM-2026-8834 was promised delivery by April "
            "14th for our Diwali campaign pre-stock. It's April 16th and we still "
            "don't have the shipment. Our contract specifies Rs 50,000/day penalty "
            "for delays beyond 48 hours. We are seriously reconsidering our "
            "logistics partnership. Please resolve immediately or we will initiate "
            "contract termination proceedings."
        ),
        "original_language": None,
        "english_translation": None,
        "media_urls": [],
        "metadata": {"company_id": "swiftlogix-001"},
    },
    {
        "event_id": "EXC-2026-0004",
        "timestamp": datetime(2026, 4, 16, 14, 20, tzinfo=UTC).isoformat(),
        "source_channel": "manual_entry",
        "sender": {"name": "Highway Patrol Desk", "role": "emergency"},
        "raw_content": (
            "EMERGENCY: Chemical tanker overturned on NH8 near Vapi, Gujarat at "
            "14:20 IST. Driver injured and admitted to local hospital. Chemical "
            "spill reported on highway — substance identified as industrial "
            "solvent. NHAI has closed a 2km stretch. Our 3 trucks are stuck behind "
            "the blockade with perishable cargo. Police and fire services on scene. "
            "PESO has been notified. Estimated road clearance: 6-8 hours minimum."
        ),
        "original_language": None,
        "english_translation": None,
        "media_urls": [],
        "metadata": {"company_id": "swiftlogix-001"},
    },
    {
        "event_id": "EXC-2026-0005",
        "timestamp": datetime(2026, 4, 16, 11, 45, tzinfo=UTC).isoformat(),
        "source_channel": "manual_entry",
        "sender": {"name": "Customs Broker", "role": "compliance"},
        "raw_content": (
            "Customs hold at Chennai port for shipment CHN-2026-442. Missing "
            "phytosanitary certificate for agricultural goods consignment. FSSAI "
            "inspection has been triggered. Expected clearance delay 2-3 business "
            "days. No perishables in this particular shipment. Documentation team "
            "working on obtaining the certificate from the exporter."
        ),
        "original_language": None,
        "english_translation": None,
        "media_urls": [],
        "metadata": {"company_id": "swiftlogix-001"},
    },
]


async def seed_live() -> None:
    """Write seed data to Firestore (emulator or prod)."""
    import os

    os.environ.setdefault("GCP_PROJECT_ID", "supply-chain-triage-dev")
    os.environ.setdefault("FIREBASE_PROJECT_ID", "supply-chain-triage-dev")

    from supply_chain_triage.core.config import get_firestore_client

    db = get_firestore_client()

    # Seed company
    await db.collection("companies").document(COMPANY["company_id"]).set(COMPANY)
    print(f"  [OK] companies/{COMPANY['company_id']}")

    # Seed exceptions
    for exc in EXCEPTIONS:
        await db.collection("exceptions").document(exc["event_id"]).set(exc)
        print(f"  [OK] exceptions/{exc['event_id']}")

    print(f"\nSeeded 1 company + {len(EXCEPTIONS)} exceptions.")


def dry_run() -> None:
    """Print seed data without writing to Firestore."""
    print("Dry-run mode — showing seed data")
    print("=" * 60)
    print(f"\nCompany: {COMPANY['name']} ({COMPANY['company_id']})")
    print(
        f"  Trucks: {COMPANY['num_trucks']}, Revenue: Rs {COMPANY['avg_daily_revenue_inr']:,}/day"
    )
    print(f"\nExceptions ({len(EXCEPTIONS)}):")
    for exc in EXCEPTIONS:
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

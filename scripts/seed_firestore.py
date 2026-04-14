"""Firestore seed script — evolves across sprints.

Sprint 0: Empty skeleton files + loader shell (this sprint).
Sprint 1: `festival_calendar.json` + `monsoon_regions.json` (Classifier tool data).
Sprint 2: `shipments.json` + `customers.json` + `companies.json` + `users.json`
          (Impact Agent data — NH-48 demo scenario).

Sprint 0 creates the `scripts/seed/` directory and empty JSON skeletons, plus
this loader shell. Each subsequent sprint populates its owned files and extends
the loader to actually write to the Firestore emulator (or prod, via --live).

Usage:
    uv run python scripts/seed_firestore.py           # dry-run (default)
    uv run python scripts/seed_firestore.py --live    # Sprint 2+ will wire this
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

SEED_DIR = Path(__file__).parent / "seed"
COLLECTIONS: tuple[str, ...] = (
    "festival_calendar",  # populated by Sprint 1 (Classifier tool data)
    "monsoon_regions",  # populated by Sprint 1
    "shipments",  # populated by Sprint 2 (Impact Agent)
    "customers",  # populated by Sprint 2
    "companies",  # populated by Sprint 2
    "users",  # populated by Sprint 2
)


def main() -> None:
    """CLI entry: dry-run or (Sprint 2+) --live seed to Firestore."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Write to Firestore (emulator if FIRESTORE_EMULATOR_HOST set, else prod). "
        "Sprint 2+ wires this; Sprint 0 is dry-run only.",
    )
    args = parser.parse_args()

    if args.live:
        print("--live: Sprint 0 does not wire Firestore writes.")
        print("       Sprint 2 (Impact Agent + Firestore) implements this.")
        print("       TODO(sprint-2): use supply_chain_triage.core.config.get_firestore_client()")
        return

    print("Dry-run mode — listing seed collection state")
    print("-" * 60)
    for collection in COLLECTIONS:
        path = SEED_DIR / f"{collection}.json"
        if not path.exists():
            print(f"  [MISSING] {collection:20s}  (file does not exist)")
            continue
        try:
            with path.open() as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"  [INVALID] {collection:20s}  ({e})")
            continue
        if not data:
            print(f"  [EMPTY]   {collection:20s}  (populated by later sprint)")
            continue
        print(f"  [READY]   {collection:20s}  ({len(data)} docs ready to seed)")


if __name__ == "__main__":
    main()

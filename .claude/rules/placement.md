---
description: Folder structure and file placement rules for src/, tests/, evals/
paths: ["src/**", "tests/**", "evals/**"]
---

# Placement rules

Every new file lands in exactly one location based on its role. If a file doesn't fit the table, the rule is wrong — ask, don't improvise.

## Folder structure

```
src/supply_chain_triage/
├── core/          — config, settings, constants used by ALL modules
├── middleware/    — FastAPI middleware (Firebase auth, request logging, tracing)
├── runners/       — FastAPI app factory + (future) Meta-Coordinator wiring
├── utils/         — pure helpers, no ADK/Firestore/Firebase imports
├── main.py        — CLI entry (supply-chain-triage = supply_chain_triage.main:cli)
└── modules/
    └── triage/
        ├── agents/
        │   └── <agent_name>/        — each agent is its OWN SUBPACKAGE
        │       ├── agent.py         — LlmAgent / SequentialAgent definition
        │       ├── prompts/         — markdown prompt files, co-located
        │       ├── schemas.py       — this agent's input/output pydantic models
        │       └── tools.py         — this agent's private tool bindings
        ├── tools/        — tools shared across this module's agents
        ├── memory/       — this module's memory/session adapters
        ├── models/       — pydantic models scoped to this module
        └── guardrails/   — this module's input/output validators

tests/
├── unit/          — fast, no external services, no I/O
├── integration/   — hits emulators (Firestore, Firebase Auth); marker: @pytest.mark.integration
├── e2e/           — full FastAPI + ADK + emulator stack (Tier 3 onwards)
└── fixtures/      — fake clients (FakeGemini, FakeFirestore, FakeSupermemory); reusable across test tiers

evals/             — ADK evalsets for `adk eval`. NOT a pytest dir. Organized per-agent.
docs/sessions/     — session notes

scripts/           — shell + python automation (setup, bootstrap, seed, deploy, claim seeding)
├── *.sh           — bash scripts (setup.sh, gcp_bootstrap.sh, deploy.sh)
├── *.py           — python scripts (seed_firestore.py, set_custom_claims.py)
└── seed/          — seed data JSONs (festival_calendar, monsoon_regions, shipments, etc.)

infra/             — infrastructure config (non-code)
├── firestore.rules          — Firestore security rules (multi-tenant)
└── firestore.indexes.json   — required composite indexes

firebase.json      — Firebase CLI config (emulators + deploy targets)
.secrets.baseline  — detect-secrets baseline (committed, regenerated via pre-commit)
```

## Placement table

| Kind of code | Place in |
|---|---|
| Agent definition | `modules/<mod>/agents/<agent_name>/agent.py` |
| Prompt markdown | The agent's own `prompts/` folder (co-located) |
| Pydantic schema used by ONE agent | That agent's `schemas.py` |
| Pydantic model shared across a module | `modules/<mod>/models/` |
| Tool used by ONE agent | That agent's `tools.py` |
| Tool shared within a module | `modules/<mod>/tools/` |
| Module memory / session adapter | `modules/<mod>/memory/` |
| Module guardrails / validators | `modules/<mod>/guardrails/` |
| FastAPI middleware | `middleware/` |
| FastAPI app/coordinator wiring | `runners/` |
| Cross-module config/settings | `core/` |
| Generic helper (no ADK/Firestore) | `utils/` |
| Test (pytest) | `tests/{unit,integration,e2e}/` |
| Test fixture / fake client | `tests/fixtures/` |
| Evalset (adk eval) | `evals/<agent_name>/` |
| Session notes | `docs/sessions/YYYY-MM-DD-<slug>.md` |
| Research doc / vault copy / Zettel | `docs/research/` |
| Bash automation script | `scripts/*.sh` (setup.sh, gcp_bootstrap.sh, deploy.sh) |
| Python automation script | `scripts/*.py` (seed_firestore.py, set_custom_claims.py) |
| Seed data (JSON) | `scripts/seed/*.json` |
| Firestore rules / indexes | `infra/firestore.rules`, `infra/firestore.indexes.json` |
| Firebase CLI config | `firebase.json` (repo root) |
| detect-secrets baseline | `.secrets.baseline` (repo root) |

## Enforcement

The `.claude/hooks/check_placement.py` PreToolUse hook rejects Edit/Write on paths outside the allowlist derived from this table. If a legitimate new file type emerges, add it to this table first, then the hook allowlist.

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
└── e2e/           — full FastAPI + ADK + emulator stack (Tier 3 onwards)

evals/             — ADK evalsets for `adk eval`. NOT a pytest dir. Organized per-agent.
docs/sessions/     — session notes
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
| Evalset (adk eval) | `evals/<agent_name>/` |
| Session notes | `docs/sessions/YYYY-MM-DD-<slug>.md` |

## Enforcement

The `.claude/hooks/check_placement.py` PreToolUse hook rejects Edit/Write on paths outside the allowlist derived from this table. If a legitimate new file type emerges, add it to this table first, then the hook allowlist.

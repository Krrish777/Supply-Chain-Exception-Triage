# Session 2026-04-14 — Structure & Rules Foundation

First rule-setting session. Set up tooling, locked architectural commitments, restructured the repo to Proposal B (module-based), and drafted `CLAUDE.md` v1.

## What we did

### Tooling set up
- **MCP server `adk-docs`** registered at project-local scope. Exposes [adk.dev/llms.txt](https://adk.dev/llms.txt) as a searchable docs index via `uvx --from mcpdoc mcpdoc`. Config in `~/.claude.json` under this project.
- **ADK skills installed globally** (`npx skills add google/adk-docs/skills -y -g`): `adk-cheatsheet`, `adk-deploy-guide`, `adk-dev-guide`, `adk-eval-guide`, `adk-observability-guide`, `adk-scaffold`. Symlinked into `~/.claude/skills/` from `~/.agents/skills/`. Active on next session start.

### Memories persisted (visible to all future sessions)
Stored in `~/.claude/projects/C--Users-777kr-Desktop-Supply-Chain-Exception-Triage/memory/`:

| File | Type | Gist |
|---|---|---|
| `feedback_prd_handling.md` | feedback | Discuss PRDs before implementing; never blind-follow |
| `feedback_simplicity_first.md` | feedback | Start simple, split when growth forces it |
| `feedback_per_feature_workflow.md` | feedback | Rules → build → test → commit; pytest ≠ adk eval |
| `feedback_session_log_to_docs.md` | feedback | Write `docs/sessions/YYYY-MM-DD-<slug>.md` at wrap-up |
| `project_architecture_a2a_vendor_free.md` | project | Module-Ready Orchestrator + A2A + ADK-swappable |
| `reference_a2a_protocol.md` | reference | A2A URLs + never hand-write A2A code |

## Decisions locked in

### 1. Structure — Proposal B (module-based)
Chose the hybrid: `src/supply_chain_triage/modules/<name>/` with layer-based layout *inside* each module. Rationale: matches the documented "Module-Ready Orchestrator" architecture (product_recap.md), supports planned Tier 2/3 agent growth and future `port_intel/` module, and makes the future Meta-Coordinator transition a `git mv` rather than a refactor.

### 2. Each agent is its own subpackage
`agents/<agent_name>/{agent.py, prompts/, schemas.py, tools.py}` rather than flat `agents/<name>.py`. Forced by Tier 2's Resolution agent (Generator-Judge pair) and the prompt-evolves-with-code coupling.

### 3. Prompts co-located with their agent
Not a shared top-level prompts folder. Prompt + schema + tools + agent definition change together.

### 4. `evals/` is a top-level sibling of `tests/`
ADK evalsets (JSON, run via `adk eval`) measure agent behavior. Pytest measures code correctness. These are different quality gates; neither substitutes for the other.

### 5. Coverage is advisory through Tier 1
Hackathon deadline 2026-04-24 is 10 days out. Hard 90% gate would push toward tautological tests on an empty codebase. Removed `--cov-fail-under=80` from `pyproject.toml` pytest `addopts`. Coverage still reports. Will harden to 90% line coverage on pure-logic folders + evalset pass rate for agents starting Tier 2.

### 6. Single `models/` — split under pressure, not preemptively
User's explicit "don't overcomplex" rule. Can split `models/` vs `schemas/` later if it hurts.

### 7. A2A protocol — never hand-write
When A2A surface is needed, scaffold via `uvx agent-starter-pack create ... --agent adk_a2a` and lift files in. `AgentCard` schema and `to_a2a()` signature shift between versions; only the starter-pack stays in sync.

### 8. Vendor-lock-free discipline
ADK imports live at the edges only: `agents/*/agent.py` and `runners/`. Forbidden in `utils/`, `core/`, `models/`, schemas, guardrails, shared tools. Codified as import rules in `CLAUDE.md`.

## Repository restructure

**Before:** `agents/hello_world.py` plus empty sibling dirs (`core/ guardrails/ memory/ middleware/ models/ runners/ tools/ utils/`).

**After:**
```
src/supply_chain_triage/
├── core/ middleware/ runners/ utils/        — top-level cross-module
├── main.py
└── modules/
    └── triage/
        ├── agents/
        │   └── hello_world/                  — placeholder; replace when we build real agents
        │       ├── agent.py
        │       └── prompts/hello_world.md
        ├── tools/ memory/ models/ guardrails/ — module-scoped
tests/{unit, integration, e2e}/
evals/
docs/sessions/
```

Every folder has `__init__.py` where it's a Python package. `evals/.gitkeep` holds the evals dir since it's not a package. Nothing deleted had content — `hello_world.py` was empty, `models/__init__.py` was empty, other top-level subdirs were empty.

## Files changed this session

- `pyproject.toml` — removed `--cov-fail-under=80` from pytest addopts (coverage advisory through Tier 1)
- `CLAUDE.md` — rewrote from scaffold-state notice to v1 structural rule set (pending merge with external rules)
- Repo restructure: see "Repository restructure" above

## Open questions / next actions

### For the user
1. **Share the external rule set** from the previous project so I can analyse, adapt, and merge into `CLAUDE.md`. This is the gating item.
2. **When ready:** populate `Makefile`, `.env.template`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`. Currently all empty.

### Deferred to next session
- Configure `.claude/settings.json` Edit/Write hooks that reject writes outside approved paths. Deferred so the hook allowlist matches the merged rule set instead of being rewritten after merge.
- Start agent hierarchy design per product_recap.md §"Next Decision Point": concrete demo scenario → per-agent prompts/schemas/tools → Firestore data model → inter-agent communication pattern → simple UI wireframe.

## Addendum — SDLC cycle locked in (same-day)

User elevated the per-feature workflow to a **non-negotiable SDLC cycle** with explicit Verification + Validation split:

```
Research → PRD proposal → (user approval) → Build → Test (verify + validate) → Push
```

- **Verification** = "is it working right?" — my perspective — pytest, ruff, mypy.
- **Validation** = "is it giving the correct answer?" — user's perspective — `adk eval` + user review of sample outputs.
- **Neither substitutes for the other.** No step skipped, ever — not for the Apr 24 deadline, not for small features.

Codified in `CLAUDE.md` as "SDLC cycle — NON-NEGOTIABLE". Memory updated (`feedback_per_feature_workflow.md` renamed in purpose to reflect full SDLC scope).

## Context handoff

Next session's first move: read `CLAUDE.md` and `docs/sessions/2026-04-14-structure-and-rules.md` (this file). Memory auto-loads via `MEMORY.md` index. When the user shares external rules, diff them against the rules in `CLAUDE.md`; flag conflicts; propose merged version for approval before editing.

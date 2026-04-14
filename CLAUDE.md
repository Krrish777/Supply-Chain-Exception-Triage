# CLAUDE.md

Guidance for Claude Code working in this repo.

> **SDLC rule of record (top):** Every feature — agent, tool, module, refactor — follows `Research → PRD → Build → Test (verify + validate) → Push`. No step skipped, not for the hackathon deadline, not ever. Full version at the bottom of this file.

## Project at a glance

Supply Chain Exception Triage — ADK multi-agent system for logistics exception triage. Full product context in `docs/product_recap.md`.

**Stack:** Google ADK + Gemini 2.5 Flash + Firestore + Firebase Auth + FastAPI. Python 3.13, `uv`-managed (`uv.lock` committed).

**Tiers:**
- Tier 1 (2026-04-24): Coordinator + Classifier + Impact, simple UI, Cloud Run
- Tier 2 (2026-05-29): + Resolution agent (Generator-Judge)
- Tier 3 (2026-06-09): + Communication agent, Route Optimization, React dashboard

## Architecture commitments

1. **Module-Ready Orchestrator** — business code lives under `src/supply_chain_triage/modules/<name>/`. Exception Triage is the first module (`modules/triage/`); future modules (e.g. `port_intel/`) drop in as siblings under a Meta-Coordinator without refactoring existing modules.
2. **A2A-first** — agents must be exposable via Google's Agent-to-Agent protocol. When an A2A surface is needed, scaffold via `uvx agent-starter-pack create ... --agent adk_a2a` and lift files in. Never hand-write `A2aAgentExecutor`, `AgentCardBuilder`, `agent.json`, or the `A2AFastAPIApplication` mount.
3. **Framework-swap tolerant** — ADK should be swappable (LangGraph, CrewAI, PydanticAI) with ~20% rewrite, not ~80%. ADK imports stay at the edges: agent definitions and runners only.

## Scoped rules (read before working)

The detailed rules live in `.claude/rules/*.md` and load automatically when you touch matching files. Think of them as just-in-time guardrails.

| File | Loads when editing | Covers |
|---|---|---|
| `placement.md` | `src/**`, `tests/**`, `evals/**` | Folder structure, what-goes-where table, hook enforcement |
| `imports.md` | `src/**` | Positive import scopes for `google.adk.*`, `firebase_admin`, `google.cloud.firestore` (backed by ruff `TID251`) |
| `api-routes.md` | `runners/**`, `middleware/**` | FastAPI dependency order, response envelopes, status codes, security-conscious error messages |
| `agents.md` | `modules/*/agents/**` | ADK callbacks, state namespacing, two-agent structured-output pattern, thinking-budget defaults, graceful degradation |
| `tools.md` | `modules/*/tools/**`, `agents/*/tools.py` | Return contract, signature, error classification, per-turn caching |
| `firestore.md` | `memory/`, `tools/`, `middleware/` | AsyncClient singleton, data model, cursor pagination, emulator setup |
| `observability.md` | `src/**` | OTel spans with `agent.name` + token usage, structured JSON logs, PII redaction |
| `deployment.md` | `.github/workflows/**`, `Dockerfile`, `infra/**` | Multi-stage uv Dockerfile, Cloud Run vs Agent Engine, Workload Identity, secrets |
| `testing.md` | `tests/**`, `evals/**` | pytest vs `adk eval` split, coverage discipline, emulator env vars |
| `architecture-layers.md` | `src/**` | Application-layer import direction (`runners → agents → tools → memory → models → core/utils`); enforced by import-linter |
| `code-quality.md` | `src/**` | Anti-bloat limits, no god functions, docstring scope, comments why-not-what |
| `new-feature-checklist.md` | `src/**` | Per-feature 7-step workflow (agent branch + FastAPI branch) |

Enforcement layers:
- **Ruff `TID251`** — vendor-import rules fail lint (`pyproject.toml`).
- **import-linter** — application-layer direction contracts fail lint (`pyproject.toml` `[tool.importlinter]`).
- **Ruff `D` + `interrogate`** — docstring style + coverage gate on boundary folders.
- **Ruff `PLR09**`** — function-shape limits (args, branches, statements, returns, locals).
- **PreToolUse hook** — `.claude/hooks/check_placement.py` rejects writes outside the placement allowlist.
- **Pre-commit** — hygiene → ruff → mypy → lint-imports → interrogate → file-size → gitleaks.
- **CI** — `uv sync --locked` as drift gate, full lint/type/test pipeline (`.github/workflows/ci.yml`).

## SDLC cycle — NON-NEGOTIABLE

Every feature follows this in order:

```
Research → PRD proposal → (user approval) → Build → Test (verify + validate) → Push
```

1. **Research.** Consult `docs/product_recap.md`, existing research notes, installed ADK skills (`adk-cheatsheet`, `adk-dev-guide`, etc.), the `adk-docs` MCP, and the web when genuinely needed.
2. **PRD proposal.** Propose a PRD (new) or PRD update (existing). Never implement a PRD as-is — always discuss gaps with the user first.
3. **Approval gate.** Implementation starts only after the user approves the adjusted PRD. If you catch yourself writing code without this gate, stop.
4. **Build.** Implement in the folder dictated by `.claude/rules/placement.md`. Respect import rules in `.claude/rules/imports.md`.
5. **Test — BOTH perspectives are required:**
   - **Verification** — "Is it working right?" Developer's perspective. pytest, ruff, mypy, security checks. The code does what the code is supposed to do.
   - **Validation** — "Is it giving the correct answer?" User's perspective. `adk eval` evalsets + user review of concrete sample outputs against domain expectations. The agent answers real exceptions correctly.
   - Neither substitutes for the other.
6. **Push.** Only after verification and validation both pass.

### Reporting "done"

When claiming a feature is done, report both sides:
- **Verification results:** pytest output, ruff/mypy status, coverage (when hardened).
- **Validation handoff:** evalset results if an evalset exists; sample inputs/outputs for the user to validate; the specific thing you need confirmed.

"Code works" ≠ "feature ships." Only the user validates.

## Commands

```bash
uv sync --all-extras                     # install runtime + test + dev + security
uv run pytest                            # run tests (coverage advisory through Tier 1)
uv run pytest tests/unit/                # run one suite
uv run pytest -m "not integration"       # skip integration
uv run ruff check . && uv run ruff format .
uv run mypy src
adk web .                                # interactive agent playground (once agents exist)
adk eval <agent_dir> <evalset>           # run evalsets
firebase emulators:start --only firestore,auth   # local emulators
```

`Makefile` wraps the most common of these as one-keystroke targets.

## Session notes discipline

At session wrap-up (or before context compaction risks loss), write a markdown summary to `docs/sessions/YYYY-MM-DD-<slug>.md`:

- Date + topic(s)
- Decisions reached + rationale
- Files changed / structure touched
- Open questions for next session

Skimmable — decisions + rationale + next steps, not transcripts.

## Pending

- [ ] Populate `.env.template` (names only — no values).
- [ ] First agent hierarchy design (per `product_recap.md` — next SDLC step).
- [ ] Flip coverage gate from advisory to `--cov-fail-under=90` on pure-logic paths at Tier 2 boundary (2026-05-29).
- [ ] Verify `.claude/rules/deployment.md` snippets against current agent-starter-pack + Cloud Run docs before first production deploy.
- [ ] Write `firestore.rules` when Tier 3 frontend starts reading Firestore directly.

---

> **SDLC rule of record (bottom):** `Research → PRD → Build → Test (verify + validate) → Push`. No step skipped — not for the hackathon, not for a small fix, not ever.

# Contributing

## Dev workflow (Spiral SDLC)

Every feature follows the project's non-negotiable SDLC cycle:

```
Research → PRD → Build → Test (verify + validate) → Push
```

- **Research** — `docs/product_recap.md`, `docs/research/` vault copies, installed ADK skills (`adk-cheatsheet`, `adk-dev-guide`), the `adk-docs` MCP. Web search only for things not covered.
- **PRD** — propose in `docs/sprints/sprint-N/prd.md`. PRDs are drafts, not contracts; discuss gaps before building.
- **Build** — strict TDD (ADR-005). Write the test first, run to confirm red, implement, run to confirm green, refactor.
- **Test — both perspectives:**
  - Verification (does the code work?) — pytest, ruff, mypy, `lint-imports`.
  - Validation (does the agent answer correctly?) — `adk eval` evalsets + user review of concrete samples.
- **Push** — only after both verification and validation pass.

Full contract: [CLAUDE.md](./CLAUDE.md) §"SDLC cycle — NON-NEGOTIABLE".

## Rules to read before editing code

The `.claude/rules/` directory is the source of truth. Rules load automatically based on which file you're editing:

| File | Loads when editing | Covers |
|---|---|---|
| `placement.md` | `src/**`, `tests/**`, `evals/**` | Folder structure + hook-enforced file placement |
| `imports.md` | `src/**` | `google.adk` / `firebase_admin` / `google.cloud.firestore` allowlists |
| `architecture-layers.md` | `src/**` | Who imports from whom (import-linter enforced) |
| `code-quality.md` | `src/**` | File size limits, docstring scope, comment discipline |
| `testing.md` | `tests/**`, `evals/**` | pytest vs `adk eval` split, coverage discipline, emulator fixtures |
| `agents.md` | `modules/*/agents/**` | ADK callbacks, state namespacing, structured-output patterns |
| `tools.md` | `modules/*/tools/**` | Return contract, error classification |
| `models.md` | `modules/*/models/**`, `agents/*/schemas.py` | Pydantic v2 patterns |
| `firestore.md` | `memory/`, `tools/`, `middleware/` | AsyncClient singleton, emulator setup |
| `api-routes.md` | `runners/**`, `middleware/**` | FastAPI dependency order, response envelopes |
| `security.md` | `middleware/**`, `core/settings.py`, `runners/**` | Firebase vs custom, custom claims, rate limiting |
| `observability.md` | `src/**` | OTel spans, structured logging, PII redaction |
| `deployment.md` | `.github/workflows/**`, `Dockerfile`, `infra/**` | Cloud Run, Workload Identity |
| `new-feature-checklist.md` | `src/**` | Per-feature 7-step workflow |

## Enforcement layers

- **Ruff** (`TID251` + `T20` + the big rule set in `pyproject.toml`) — import rules are LINT errors, not advisory. Run `uv run ruff check .`.
- **Mypy** (`strict = true`) — full type coverage on `src/`. Run `uv run mypy src`.
- **Import-linter** — application-layer direction. Run `uv run lint-imports`.
- **`.claude/hooks/check_placement.py`** — `Edit`/`Write` tool calls are blocked on paths outside the placement allowlist.
- **Pre-commit** — ruff, mypy, lint-imports, gitleaks/detect-secrets. Runs on every commit once `.pre-commit-config.yaml` is populated.
- **CI** — same gates on push + PR. Integration tests against Firestore emulator nightly.

## TDD policy (ADR-005)

Strict TDD is the only accepted workflow. No code is committed without a test committed in the same or preceding commit.

**Exceptions** (no test required):
1. `scratch/` directories — must be deleted before PR.
2. Prompt markdown (`prompts/*.md`) — tested via `adk eval`, not pytest.
3. Infrastructure config (`pyproject.toml`, `.github/workflows/*.yml`, `firestore.rules`).
4. Documentation files.
5. Generated code (excluded from coverage + TDD).

Everything else — schemas, middleware, agents, tools, sanitizers, memory adapters, runners — is strict TDD.

## Sprint workflow (Spiral SDLC)

Each sprint is one iteration through four phases (per ADR-006):
1. **Plan** — Research → PRD → Test Plan → user review.
2. **Risk** — Pre-mortem → ADRs → threat notes.
3. **Engineer** — TDD cycles, security checks.
4. **Evaluate** — Test report, code review, retrospective.

Each sprint produces 9 artifacts in `docs/sprints/sprint-N/`: `prd.md`, `test-plan.md`, `risks.md`, `adr-*.md`, `security.md`, `impl-log.md`, `test-report.md`, `review.md`, `retro.md`.

## PR checklist

- [ ] New feature has a PRD in `docs/sprints/sprint-N/prd.md` (approved before coding began).
- [ ] Tests were written before implementation (check commit order).
- [ ] `uv run pytest` green (including any new tests).
- [ ] `uv run ruff check .` green.
- [ ] `uv run mypy src` green.
- [ ] `uv run lint-imports` green (5+ contracts kept).
- [ ] For agent additions: evalset at `evals/<agent_name>/` green via `adk eval`.
- [ ] Session note at `docs/sessions/YYYY-MM-DD-<slug>.md` if the change is non-trivial.

## Session notes

At session wrap-up, write a markdown summary to `docs/sessions/YYYY-MM-DD-<slug>.md`:

- Date + topic(s)
- Decisions reached + rationale
- Files changed / structure touched
- Open questions for next session

Skimmable — decisions + rationale + next steps, not transcripts.

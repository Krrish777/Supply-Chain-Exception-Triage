---
title: "Sprint 0 Retrospective"
type: deep-dive
domains: [supply-chain, sdlc]
last_updated: 2026-04-14
status: active
---

# Sprint 0 Retrospective

> Per ADR-006 Spiral SDLC Evaluate phase. Start / Stop / Continue for Sprint 1.

## Sprint summary

- **Window:** 2026-04-14 (single-day compressed — planned 2026-04-10 to 2026-04-12 per PRD v1; rebased to today per PRD v2).
- **Scope:** Secure Foundation + Test Harness + Docs Infrastructure.
- **Outcome:** Shipped. Phase A (Plan) + Phase B (Risk) + Phase C (Engineer, C1-C10) + Phase C Remediation (CR1-CR9) + Logger phase (L1-L5, L7-L9) + Phase D (this file). **L6 retrofit deferred** — boilerplate, adds incrementally as agents land.
- **§17 gate:** 8 items green, 7 waiting on user-owned artifacts + user smoke-tests (see `test-report.md` §"Sprint 0 §17 acceptance criteria — self-check").

## Start

What should we start doing next sprint?

- **Run `superpowers:code-reviewer` mid-sub-phase, not just at sprint close.** The Sprint 0 reviewer caught 7 real issues in one pass — if it had run after C4 (not after C10), fixes would have been cheaper. Cost is ~1 minute of reviewer time; benefit is catching issues before downstream work compounds them.
- **Add structlog `LogCapture` fixture usage to Sprint 1's first test.** We ended Sprint 0 with the fixture + rule + 12 tests for the logger. Sprint 1 Classifier tests should immediately start with `def test_classifier_foo(log_output)` to build the muscle memory.
- **Pin Gemini model in tests that hit real Gemini.** Sprint 0's one integration test (`test_hello_world.py::test_agent_responds_to_greeting`) skips without `GEMINI_API_KEY`. When Sprint 1 adds real Gemini calls for Classifier evals, pin `gemini-2.5-flash` version in the test fixture so we don't silently upgrade mid-sprint.
- **Use `bind_contextvars` over raw `ContextVar.set()` from day one in Sprint 1.** The Zettel + logger + rule are in place; tools and agents should default to `structlog.contextvars.bind_contextvars` for anything that should flow through the log chain.

## Stop

What should we stop doing?

- **Stop writing lengthy explanatory docstrings when the rule file already says it.** A few Sprint 0 files (e.g. `audit_log.py`, `core/config.py`) have 20-line docstrings explaining architecture context. Rule-level concerns belong in `.claude/rules/*.md`; the code file should say "see `.claude/rules/X.md` §Y" and leave the explanation there. Avoids drift.
- **Stop auto-importing types into `__init__.py` if they're not part of the public API.** `modules/triage/models/__init__.py` re-exports 14 names. The §17 #9 smoke-import test needed 7; the rest ride along. Future modules: re-export only the public API.
- **Stop accepting "unused noqa" warnings.** Sprint 0 accumulated several `# noqa: BLE001` / `# noqa: ARG002` comments that were later removed by ruff --fix. If a noqa is unused, the code has changed — the comment is stale. Fold into review gate.

## Continue

What worked that we should keep?

- **Strict TDD cycle.** Tests-first then implement was visible in every sub-phase and caught bugs before they existed (e.g. the async-def-missing-await in memory stub tests surfaced immediately).
- **Per-file TID251 exceptions (not global relaxation).** Four well-documented exceptions: `core/config.py` (DI chokepoint), `scripts/**` (admin tooling), `utils/logging.py` (the log entrypoint), and the standard layer exceptions. Each is commented in `pyproject.toml`. Future exceptions should follow this template.
- **Reviewer-then-fix chain (CR1-CR9).** Running `superpowers:code-reviewer` before Phase D Evaluate produced exactly the findings worth fixing — and the remediation pass took ~1h total. Worth the cost.
- **Vault-Zettels-before-plan.** For anything I researched, writing a Zettel to `Obsidian-Notes-Vault` FIRST (before coding) preserved the reasoning. Two Sprint 4 decisions are already flagged in Zettels and won't need to be re-discovered.
- **Session logs to `docs/sessions/`.** Lets the user pick up where we left off without replaying the whole conversation.
- **PRD v1 → v2 reconciliation explicit section.** "Changes from v1" at the top of PRD v2 — anyone reading the new file sees exactly what moved. Works for PRD updates in future sprints too.

## What surprised us

1. **Pre-existing `check_placement.py` bugs** (fnmatch `**` + lstrip dotfiles). Silent failures. Caught by a 27-case sanity matrix. Lesson: add a self-test to any enforcement hook.
2. **`[tool.pytest.ini]` typo** — should be `ini_options`. Had been there since project init, silently ignoring `asyncio_mode=auto`. Caught by `pytest --collect-only` warning. Lesson: always look at pytest warnings, even the "Unknown config option" ones.
3. **Vault Coordinator spec internal inconsistency** — documented in a Zettel so the next person who reads that spec has a pointer.
4. **`BaseHTTPMiddleware` is scheduled for Starlette deprecation.** Sprint 4 will need a refactor. Zettel'd.
5. **`structlog.contextvars` async/sync gotcha in FastAPI.** My original logger used a raw ContextVar + custom processor. The canonical pattern (`bind_contextvars` + built-in `merge_contextvars`) is both simpler AND handles the hybrid case better. Logger rewritten, Zettel'd.

## Metrics

| Metric | Sprint 0 | Target | Notes |
|---|---|---|---|
| Tests added | 57 | ≥32 | Almost double the target — the logger phase added 12, and middleware/main added a few extra regression guards |
| Coverage % (pure-logic) | 92% | ≥80% (Tier 1 advisory) | Above the Tier 2 90% gate already |
| TID251 violations | 0 | 0 | Fixed in CR1 |
| Layer contract breaks | 0 | 0 | All 5 import-linter contracts kept throughout |
| Sprint budget (hours) | ~12 | ~12-14 | On budget; phase A + B ran long, phase C was tight, D is short |
| Docs produced | 35+ | 16 minimum | 8 ADRs + 5 templates + 2 security + README/CONTRIBUTING/SECURITY + 5 Spiral artifacts (this file one of them) + 6 research vault copies + 7 Zettels + 1 ADA digest |
| Ruff errors at gate | 0 | 0 | ✅ |
| Mypy errors at gate | 0 | 0 | ✅ |

## Decisions deferred

- **L6 — retrofit lifecycle events into every middleware / core / memory file.** Boilerplate. Defer to Sprint 1 as agents land; add lifecycle events where debugging benefits.
- **OTel span wiring + Cloud Run trace-correlation fields** — Sprint 1+ per `observability.md`. Logger has the processor seam; wiring is additive.
- **React frontend** — Sprint 5 Should-Have trim; `adk web` fallback if time runs out.
- **Supermemory real integration** — Sprint 4 Should-Have. Sprint 0 fake client works for Sprints 1-3.
- **`check_revoked=True` on privileged routes** — Sprint 4 security hardening.

## Follow-up items

- [ ] User populates `.pre-commit-config.yaml`, `.github/workflows/{ci,security,deploy}.yml`, `Makefile`, `.env.template`.
- [ ] User runs `scripts/gcp_bootstrap.sh` against the actual GCP project (needs billing + gcloud auth).
- [ ] User runs `adk web` against `modules/triage/agents/hello_world/agent.py` to confirm §17 #3.
- [ ] User runs `firebase emulators:start --only firestore,auth` and `uv run pytest tests/integration` to confirm §17 #4.
- [ ] User runs `adk eval src/supply_chain_triage/modules/triage/agents/hello_world evals/hello_world/greeting.evalset.json` to confirm §17 #17.
- [ ] Tag `v0.1.0-sprint-0` after §17 gate fully green.

## Sprint 1 kick-off notes

What should Sprint 1's PRD emphasize based on what we learned here?

- **Classifier is a single-agent sprint.** Don't scope-creep into Impact or Coordinator. That's Sprint 2 and Sprint 3.
- **Seed `festival_calendar.json` + `monsoon_regions.json`** early in Sprint 1 — the Classifier tools (`get_festival_context`, `get_monsoon_status`) depend on them. Sprint 1 test-plan should include a "seed data present" acceptance criterion.
- **Classifier Severity Validator Rule 3** is concrete code (5% threshold). Sprint 1 test-plan writes that rule as a pure-function test (no LLM) — validator logic vs the LLM's severity output are separate concerns.
- **Write the Classifier evalset at Day 1**, not Day 2. Sprint 0 left `evals/hello_world/greeting.evalset.json` as the format exemplar.
- **Use `log_agent_invocation`** from the very first Classifier test — builds the observability habit that compounds across agents.

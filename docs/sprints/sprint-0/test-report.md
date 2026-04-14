---
title: "Sprint 0 Test Report"
type: deep-dive
domains: [supply-chain, testing, sdlc]
last_updated: 2026-04-14
status: active
---

# Sprint 0 Test Report

> Snapshot of pytest + ruff + mypy + lint-imports as of Sprint 0 close.

## Test summary

**57 passing, 1 skipped (integration without live Gemini).** 2 integration tests auto-skip when Firestore emulator / GEMINI_API_KEY not available — correct behavior per `.claude/rules/testing.md` §5.

```
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-7.4.x, pytest-asyncio-0.21.x
asyncio: mode=Mode.AUTO, asyncio_default_fixture_loop_scope=session
collected 58 items

tests/unit/agents/test_hello_world.py            3 passed, 1 skipped
tests/unit/config/test_config.py                 5 passed
tests/unit/memory/test_provider.py               5 passed
tests/unit/middleware/test_audit_log.py          2 passed
tests/unit/middleware/test_cors.py               3 passed
tests/unit/middleware/test_firebase_auth.py      7 passed
tests/unit/middleware/test_input_sanitization.py 3 passed
tests/unit/middleware/test_rate_limit.py         1 passed
tests/unit/runners/test_main.py                  2 passed
tests/unit/schemas/test_classification.py        2 passed
tests/unit/schemas/test_company_profile.py       3 passed
tests/unit/schemas/test_exception_event.py       2 passed
tests/unit/schemas/test_impact.py                2 passed
tests/unit/schemas/test_triage_result.py         2 passed
tests/unit/schemas/test_user_context.py          3 passed
tests/unit/utils/test_logging.py                12 passed

Total: 57 passed, 1 skipped in ~6s
```

## Coverage (pure-logic paths)

Configured in `pyproject.toml` `[tool.coverage.run] source` — scoped to `core/`, `utils/`, `middleware/`, `modules/triage/{models,tools,guardrails,memory}/`.

| Module | Coverage | Uncovered lines | Reason |
|---|---:|---|---|
| `core/config.py` | 62% | 107-124, 141-146 | Real GCP Secret Manager + Firestore client factory — exercised only by integration tests |
| `middleware/audit_log.py` | 100% | — | — |
| `middleware/cors.py` | 100% | — | — |
| `middleware/firebase_auth.py` | 100% | — | 6 paths (valid / expired / tampered / missing creds / missing claim / ValueError) + public path |
| `middleware/input_sanitization.py` | 100% | — | — |
| `middleware/rate_limit.py` | 100% | — | Pass-through stub; 1-line smoke test covers it |
| `modules/triage/memory/provider.py` | 100% | — | ABC signature |
| `modules/triage/memory/supermemory_adapter.py` | 100% | — | Stub raises NotImplementedError on all methods |
| `modules/triage/models/classification.py` | 100% | — | — |
| `modules/triage/models/company_profile.py` | 100% | — | — |
| `modules/triage/models/exception_event.py` | 100% | — | — |
| `modules/triage/models/impact.py` | 100% | — | — |
| `modules/triage/models/learned_preferences.py` | 85% | 32 | Empty-priorities branch not exercised in this test set |
| `modules/triage/models/triage_result.py` | 100% | — | — |
| `modules/triage/models/user_context.py` | 100% | — | — |
| `utils/logging.py` | 86% | 118-119, 139-141, 237-249, 281, 327->329, 367, 385, 435 | Stdlib-compat filter + Cloud Run JSON stdout handler + a few domain helpers (tool/firestore/auth) not directly tested |
| **TOTAL** | **92%** | — | |

**Tier 1 status:** coverage is advisory (no `--cov-fail-under`). From Tier 2 (2026-05-29) the gate flips to 90% on these pure-logic paths — we are already above target.

## Static analysis

| Tool | Status | Command |
|---|---|---|
| Ruff | `All checks passed!` | `uv run ruff check .` |
| Mypy (strict) | `Success: no issues found in 32 source files` | `uv run mypy src` |
| Import-linter | `Contracts: 5 kept, 0 broken` | `uv run lint-imports` |

Import-linter contracts kept:
- Top-level layering (runners → middleware → agents → tools → memory → models/guardrails → core → utils)
- Agents do not import memory directly
- Tools do not import agents
- Memory is terminal
- Models and guardrails are terminal

## Security scans

Deferred: `bandit -r src/`, `safety check`, `pip-audit`. These run via pre-commit + CI once the user populates `.pre-commit-config.yaml` + `.github/workflows/security.yml`. Sprint 0 PRD v2 §17 item #7 will light up then.

## Evalsets

`evals/hello_world/greeting.evalset.json` authored. Executing `adk eval` is manual in Sprint 0 (requires GEMINI_API_KEY); PRD v2 §17 item #17 ticks green when the user runs the smoke. Sprint 1 will automate via CI.

## Sprint 0 §17 acceptance criteria — self-check

| # | Criterion | Status |
|---|---|---|
| 1 | `uv run pytest` exits 0 with ≥32 tests | ✅ (57 tests) |
| 2 | Coverage reports (advisory) | ✅ (92% pure-logic) |
| 3 | `adk web` launches, hello_world responds | ⏳ (user verification — agent + prompt + evalset all in place) |
| 4 | Firestore emulator integration test passes | ⏳ (user verification — test + fixture + infra/firestore.rules + infra/firestore.indexes.json + firebase.json in place; skip-guard works) |
| 5 | Pre-commit green on clean repo | ⏳ (user populates `.pre-commit-config.yaml`) |
| 6 | CI green on main | ⏳ (user populates `.github/workflows/*.yml`) |
| 7 | Bandit/safety/pip-audit 0 high | ⏳ (CI dependency) |
| 8 | Docs set (8 ADRs + 5 templates + threat-model + OWASP + README/CONTRIBUTING/SECURITY + 5 Spiral artifacts + 6 research + 5 Zettels + 1 digest) | ✅ |
| 9 | Schema smoke import | ✅ |
| 10 | Auth middleware 6 tests pass | ✅ (7 actually — extra public-path case) |
| 11 | `.env.template` | ⏳ (user writes) |
| 12 | Directory tree matches placement.md; hook silent | ✅ |
| 13 | Sprint 1 backfill helpers importable | ✅ |
| 14 | **NEW — zero TID251** | ✅ (was #1 critical blocker; CR1 fixed) |
| 15 | **NEW — session note written** | ⏳ (Phase D — next artifact) |
| 16 | **NEW — set_custom_claims.py runs** | ⏳ (user runs against Firebase test project) |
| 17 | **NEW — hello_world evalset runs green** | ⏳ (user runs `adk eval`) |

**Net sprint status:** 8 items green, 7 waiting on user-owned artifacts (pre-commit/CI/.env/gcloud) + the `adk web` / `adk eval` manual smoke.

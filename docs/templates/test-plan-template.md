---
title: "Sprint N Test Plan"
type: deep-dive
domains: [supply-chain, testing, sdlc]
last_updated: YYYY-MM-DD
status: active
confidence: high
sources: []
---

# Sprint N Test Plan

> Given/When/Then test cases. Written **test-first per ADR-005 (Strict TDD)**: each test MUST be written and run to confirm failure before any implementation code.

## Test conventions

- Framework: `pytest >= 7.3.2` + `pytest-asyncio >= 0.21.0`
- Python: **3.13**
- Async tests: `asyncio_mode = "auto"` (don't annotate manually)
- Layout: `tests/unit/<area>/test_<subject>.py`
- Auth mocking: `firebase_admin.auth.verify_id_function` mocked via `pytest-mock`
- Coverage: advisory through Tier 1; hardens to 90% on pure-logic at Tier 2
- Evalsets (NOT pytest): `evals/<leaf_agent>/*.evalset.json`, run by `adk eval`. Not on Coordinators (ADK bug #3434).

---

## Area 1: <Area name> — N tests

### Test 1.1: <behavior>
- **Given** ...
- **When** ...
- **Then** ...

### Test 1.2: <behavior>
- **Given** ...
- **When** ...
- **Then** ...

---

## Area 2: <Area name> — N tests

...

---

## Test execution commands

```bash
uv run pytest -m "not integration"             # fast unit tests
uv run pytest                                  # full suite (needs emulators)
uv run pytest --cov                            # coverage report
uv run pytest tests/unit/<area>/test_x.py::test_behavior -v
pre-commit run --all-files
adk eval modules/<mod>/agents/<name> evals/<name>/<suite>.evalset.json
```

---

## Coverage target

- Through Tier 1 (2026-04-24): ADVISORY.
- From Tier 2: gate at 90% on pure-logic paths.
- Critical paths (middleware, sanitizers, schemas): target ≥95% once gating.

---

## Test budget

| Area | Tests |
|---|---|
| ... | N |
| **Total** | **N** |

---

## Exit criteria

All tests green. Pre-commit passes. CI green on main. `bandit`/`safety`/`pip-audit` clean.

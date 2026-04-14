---
description: pytest + adk eval split, test-tree mirror, conftest patterns, auth A/B, Gemini mocking, coverage targets, per-endpoint checklist
paths: ["tests/**", "evals/**"]
---

# Testing rules

pytest answers "does the code work?" — the developer's perspective (verification). `adk eval` answers "does the agent give the right answer?" — the user's perspective (validation). Neither substitutes for the other.

## 1. Test pyramid

| Layer | Lives in | Purpose | External services |
|---|---|---|---|
| Unit | `tests/unit/` | Pure logic, tool I/O wrapped in mocks, schema round-trips, guardrail validation | None |
| Integration | `tests/integration/` | Firestore emulator, Firebase Auth emulator, real Pydantic boundaries | Emulators only |
| E2E (Tier 3+) | `tests/e2e/` | Full FastAPI + ADK + emulators | Emulators only |
| Fixtures | `tests/fixtures/` | Fake clients (FakeGemini, FakeFirestore, FakeSupermemory) reusable across tiers | None |
| Evalsets | `evals/<agent_name>/` | Agent behavioral correctness, tool trajectories | Gemini (cassette or live — see §6) |

Marker: `@pytest.mark.integration` on integration tests. `addopts` uses `--strict-markers`.

## 2. Test-tree mirror

```
tests/
  conftest.py                                   # env vars, readiness probes
  unit/
    core/test_settings.py
    utils/test_<helper>.py
    middleware/test_firebase_auth.py
    modules/triage/
      models/test_exception.py
      guardrails/test_input_validator.py
      tools/test_<shared_tool>.py               # module-shared tools
      agents/<agent>/test_tools.py              # agent-private tools only
      agents/<agent>/test_callbacks.py
  integration/
    conftest.py                                 # emulator clients, auth-emulator token mint
    memory/test_firestore_session.py
    api/test_exceptions.py                      # route-groups, not source paths
    api/test_triage.py
  fixtures/                                     # FakeGemini, FakeFirestore, FakeSupermemory
  e2e/                                          # Tier 3
evals/<agent>/evalset.json                      # leaf agents only
```

Rule: `tests/unit/**` mirrors `src/supply_chain_triage/**` 1:1. `tests/integration/api/` mirrors route-groups, not source paths.

## 3. Coverage discipline

- **Through Tier 1 (2026-04-24)**: advisory. `--cov-report=term-missing --cov-report=xml`, no `--cov-fail-under`.
- **From Tier 2**: per-folder gate (see table), aggregate `--cov-fail-under=85` on scoped `[tool.coverage.run] source`.
- **Never tautological** — if you can't write a meaningful assertion, delete the test. 70% real coverage beats 95% trivial.

| Folder | Tier 2 gate |
|---|---|
| `core/`, `utils/`, `middleware/` | 90% line + branch |
| `modules/*/models/`, `schemas.py` | 95% |
| `modules/*/guardrails/` | 95% |
| `modules/*/tools/` | 85% |
| `modules/*/memory/` | 80% |
| `modules/*/agents/**` | excluded — validated by `adk eval` pass-rate |
| `runners/` | 70% |

## 4. Evalsets

- Every agent ships with at least one evalset from its first merge. No "we'll add evals later".
- Evalsets live in `evals/<agent_name>/`, one per **leaf** agent. **Not on Coordinators** — ADK bug on sub-agent trajectory scoring (adk-python#3434).
- Metrics: `tool_trajectory_avg_score`, `response_match_score` (structured/JSON outputs only), `rubric_based_final_response_quality_v1` (semantic asserts).
- **Never** `response_match_score=1.0` on free-text — model revs will break it.
- Run via `adk eval <agent_dir> <evalset>`.

## 5. pytest config

In `pyproject.toml` under `[tool.pytest.ini_options]`:
- `asyncio_mode = "auto"` — no `@pytest.mark.asyncio` boilerplate.
- `asyncio_default_fixture_loop_scope = "session"` — session-scoped async fixtures work with auto mode.
- `--strict-markers --strict-config`.

**Hypothesis gotcha:** `asyncio_mode = "auto"` is incompatible with Hypothesis (pytest-asyncio#258). If Hypothesis lands, either switch to `strict` mode or scope Hypothesis tests via a separate fixture pattern.

## 6. `conftest.py` patterns

Top `tests/conftest.py` — set emulator env vars **before any client constructs**:

```python
import os
os.environ.setdefault("GCLOUD_PROJECT", "sct-test")
os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "localhost:8080")
os.environ.setdefault("FIREBASE_AUTH_EMULATOR_HOST", "localhost:9099")
```

Integration `tests/integration/conftest.py`:

```python
import pytest, httpx
from google.cloud import firestore
from httpx import AsyncClient, ASGITransport

@pytest.fixture(scope="session")
async def firestore_client():
    client = firestore.AsyncClient(project="sct-test")
    yield client

@pytest.fixture(autouse=True)
async def _clear_firestore():
    yield
    async with httpx.AsyncClient() as c:
        await c.delete(
            "http://localhost:8080/emulator/v1/projects/sct-test/databases/(default)/documents"
        )

@pytest.fixture
async def async_client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
```

**Factories:** plain builder functions (`build_exception(**overrides)`) — no `factory_boy` at Tier 1-2.

**ADK sessions:** default to `InMemorySessionService` in unit + most integration tests. Only `tests/integration/memory/` exercises `FirestoreSessionService` against the emulator.

**xdist:** derive `GCLOUD_PROJECT = f"sct-test-{worker_id}"` from the xdist `worker_id` fixture to avoid emulator collisions across parallel workers.

## 7. Auth in tests — A/B rule

| Test kind | Pattern |
|---|---|
| Unit + most integration | **Dependency override** — `app.dependency_overrides[get_current_user] = lambda: FirebaseUser(uid="test-user", tier=1, tenant_id="acme")`. Always clear in teardown. |
| Middleware integration only | **Firebase Auth emulator** — mint via `auth.create_user(uid=...)` → `auth.create_custom_token(uid)` → POST emulator `/identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key=fake-api-key` → use returned `idToken`. |

Keep the rule: `FIREBASE_AUTH_EMULATOR_HOST` is **only** set in test fixtures, never in app code, never in Cloud Run env — Firebase Admin SDK honors it unconditionally and accepts forged tokens.

## 8. Mocking Gemini

Three layers, pick per test kind:

1. **Tool unit tests** — don't touch Gemini. Pass a `ToolContext` stub.
2. **Rare pytest agent smoke tests** — `pytest-recording` (VCR) cassettes. Record once with `--record-mode=once`, commit cassettes under `tests/fixtures/cassettes/`, replay in CI. Never live Gemini from pytest in CI.
3. **Agent behavior** — `adk eval` only. Live Gemini (or cached via an adk-eval-level cassette), gated to pre-merge / nightly, not per-PR.

**Banned:** custom Gemini stubs rolled per-test. Use `pytest-recording` for replay consistency.

## 9. 3-tier agent test strategy

| Target | Test kind | Tooling |
|---|---|---|
| Tools | pytest unit | `mockfirestore` for unit, `ToolContext` stub, assert return shape + state mutations + error taxonomy |
| Callbacks | pytest unit | `MagicMock(spec=CallbackContext)`, assert `state` mutations and return values |
| Guardrails | pytest unit | Pure validators — assert pass/fail on edge cases |
| Agent end-to-end | `adk eval` | Evalset JSON with `expected_tool_use` (trajectory), rubric scoring |

**Why not pytest an `LlmAgent`:** mocked → tautology on the mock; live → non-deterministic even at `temperature=0` + seed, burns budget. `adk eval` is purpose-built with multi-invocation judging and threshold tolerance.

**Coordinator testing:** no evalset (ADK bug adk-python#3434). Instead, a pytest smoke test with a stub `LlmAgent` that asserts the right leaf was invoked.

## 10. Per-endpoint checklist

Minimum scenarios per route:

| # | Scenario | Applies to |
|---|---|---|
| 1 | 200 happy path | All |
| 2 | 201 persists doc (integration, emulator) | `POST /exceptions` |
| 3 | 401 no token | All |
| 4 | 403 wrong tenant / tier | All |
| 5 | 404 missing resource | `GET /exceptions/{id}/...` |
| 6 | 422 schema violation | POST/PUT/PATCH |
| 7 | Idempotency / duplicate key | `POST /exceptions` |
| 8 | SSE disconnect mid-stream | streaming `/triage` |
| 9 | Rate-limit 429 | once middleware lands |
| 10 | Auth-emulator token round-trip | ≥1 per route-group |

List endpoints: add cursor pagination + tenant-scoping tests.

## 11. Tool picks

| Tool | Adopt? |
|---|---|
| `pytest-asyncio` auto | ✅ (already in deps) |
| `pytest-mock` | ✅ (already in deps) |
| `pytest-cov` | ✅ (already in deps) |
| `httpx.AsyncClient` + `ASGITransport` | ✅ (FastAPI ≥0.115 idiom) |
| `respx` | ✅ added to `[test]` optional-deps — use when external HTTP calls appear |
| `pytest-recording` (VCR) | ✅ added to `[test]` optional-deps — for cassette-style Gemini replay |
| `mockfirestore` | ✅ unit-only (no indexes / transactions fidelity) |
| `freezegun` | ➕ add only when time-control needed (no `pytest-freezegun` wrapper) |
| `pytest-firestore` | ❌ skip (abandoned; roll our own fixtures) |
| `factory_boy` | ❌ skip Tier 1-2 (plain builders) |

## 12. Anti-patterns

1. **Hard-coded emulator ports** without a readiness probe — CI port collisions. Use `localhost:<env-override-or-default>` + retry probe.
2. **Live Gemini in pytest** — burns budget, non-deterministic. Route live-model runs through `adk eval`.
3. **Evalsets pinned to exact Gemini strings** via `response_match_score=1.0` on free text — breaks on model revs. Use rubric-based scoring.
4. **pytest asserting on `LlmAgent` output** — tautology (mocked) or flaky (live). Forbidden.
5. **Skipping `dependency_overrides.clear()`** in fixture teardown — cross-test auth leakage.
6. **Shared project-id across `pytest-xdist` workers** — emulator data collisions. Derive per-worker project-id.
7. **`FIREBASE_AUTH_EMULATOR_HOST` anywhere but tests** — Firebase Admin SDK accepts forged tokens.
8. **Coverage-driven trivial tests** — write tests because the code needs verification, not because coverage says so.

## 13. Security-conscious test data

- Tests may use `assert` (`S101` waived for `tests/**`).
- Tests may contain fake tokens/passwords for emulators (`S105`, `S106` waived).
- Tests may import banned APIs for mocking (`TID251` waived for `tests/**`).
- Docstrings not required (`D` waived for `tests/**`).
- Real secrets never committed — gitleaks pre-commit catches attempts.

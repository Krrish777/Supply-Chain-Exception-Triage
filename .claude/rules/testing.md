---
description: pytest vs adk eval split, emulator env, coverage discipline
paths: ["tests/**", "evals/**"]
---

# Testing rules

pytest answers "does the code work?" — the developer's perspective (verification). `adk eval` answers "does the agent give the right answer?" — the user's perspective (validation). Neither substitutes for the other.

## 1. Test pyramid

| Layer | Lives in | Purpose | External services |
|---|---|---|---|
| Unit | `tests/unit/` | Pure logic, tool I/O wrapped in mocks, schema round-trips, guardrail validation | None |
| Integration | `tests/integration/` | Firestore emulator, Firebase Auth emulator, real pydantic boundaries | Emulators only |
| E2E (Tier 3+) | `tests/e2e/` | Full FastAPI + ADK + emulators | Emulators only |
| Evalsets | `evals/<agent_name>/` | Agent behavioral correctness, tool trajectories | Gemini (live or cached) |

Marker: `@pytest.mark.integration` on integration tests. `addopts` uses `--strict-markers`.

## 2. Coverage discipline

- **Through Tier 1 (2026-04-24)**: advisory. `--cov-report=term-missing --cov-report=xml`, no `--cov-fail-under`.
- **From Tier 2**: gate at 90% on pure-logic paths, scoped in `[tool.coverage.run] source = [...]`. Agents are validated by evalsets, not coverage.
- **Never tautological** — if you can't write a meaningful assertion, delete the test. 70% real coverage beats 95% trivial.

## 3. Evalsets

- Every agent ships with at least one evalset from its first merge. No "we'll add evals later".
- Evalsets live in `evals/<agent_name>/`, one per leaf agent. **Not on Coordinators** — known ADK bug on sub-agent trajectory scoring (adk-python#3434).
- Metrics: `tool_trajectory_avg_score`, `response_match_score`, and `rubric_based_final_response_quality_v1` where appropriate.
- Run via `adk eval <agent_dir> <evalset>`.

## 4. pytest config

Already set in `pyproject.toml`:
- `asyncio_mode = "auto"` — no `@pytest.mark.asyncio` boilerplate.
- `--strict-markers --strict-config`.

**Gotcha:** `asyncio_mode = "auto"` is incompatible with Hypothesis (pytest-asyncio#258). If Hypothesis lands, either switch to `strict` mode or scope Hypothesis tests via a separate fixture pattern.

## 5. Emulator fixtures

Integration tests set:
```bash
FIRESTORE_EMULATOR_HOST=localhost:8080
FIREBASE_AUTH_EMULATOR_HOST=localhost:9099
GCLOUD_PROJECT=sct-test
```

Session-scoped pytest fixture:
1. Spawns `firebase emulators:start --only firestore,auth`.
2. Waits for ports.
3. Yields clients.
4. On teardown: DELETE `http://localhost:8080/emulator/v1/projects/sct-test/databases/(default)/documents` to clear state between test sessions.

Per-test teardown: same DELETE, scoped to each test.

**`mockfirestore`** only for unit tests of pure tool logic. Does NOT emulate transactions, indexes, or security rules accurately.

## 6. `FIREBASE_AUTH_EMULATOR_HOST` discipline

- Set in: test fixtures, local dev only.
- **Never** set in Cloud Run env (dev/staging/prod). The auth emulator accepts forged tokens when this env var is set — Firebase Admin SDK honors it unconditionally.

## 7. Testing tools vs agents

- **Tools**: unit test with `mockfirestore` + a `ToolContext` stub. Assert return shape, error classification, `tool_context.state` mutations.
- **Callbacks**: unit test as plain functions with mocked `CallbackContext`.
- **Guardrails**: unit test as pure validators.
- **Agents**: evalsets only. Don't pytest an `LlmAgent` — you'll write tautologies.

## 8. Security-conscious test data

- Tests may use assert (`S101` waived for `tests/**`).
- Tests may contain fake tokens/passwords for emulators (`S105`, `S106` waived).
- Real secrets never committed — gitleaks pre-commit catches attempts.

---
title: "Sprint 0 Code Review"
type: deep-dive
domains: [supply-chain, sdlc, review]
last_updated: 2026-04-14
status: active
---

# Sprint 0 Code Review

> Findings from `superpowers:code-reviewer` agent (2026-04-14, run against the 27-file Phase C1-C4 diff) + remediation status.

## Reviewer brief (for reference)

**Scope:** Sprint 0 Phase C1-C4 — 27 files in the git working tree. The `main` branch baseline is empty; this is the first substantive code landing.

**Standards:** `.claude/rules/*.md` + `CLAUDE.md` + `docs/sprints/sprint-0/prd.md` (v2) + `docs/sprints/sprint-0/test-plan.md` + all 8 ADRs. Plus vault Zettels flagged in the brief as items NOT to re-discover.

## Critical findings (Sprint 0 gate blockers) — all remediated

### 1. `scripts/set_custom_claims.py` violates TID251 ✅ FIXED (CR1)

Reviewer found that `firebase_admin` imports in `scripts/set_custom_claims.py` violate `.claude/rules/imports.md` (allowlist was `modules/*/memory/`, `modules/*/tools/`, `middleware/`). This broke `uv run ruff check .` → §17 #14 fail.

**Remediation:**
- Added `"scripts/**" = ["TID251", "T201", "T203"]` per-file-ignore in `pyproject.toml`.
- Extended `.claude/rules/imports.md` to explicitly allow `firebase_admin` + `google.cloud.firestore` in `scripts/` (documented reasoning: server-admin tooling, not request-path code).

### 2. Ruff failure set ✅ FIXED (CR2)

15 errors aggregated: `PLR0911` in `firebase_auth.dispatch` (7 returns), dead `noqa: BLE001`, unused `import pytest`, empty `TYPE_CHECKING` blocks, raw-string docstrings, missing `D103` on `scripts/*.py main()`, `PTH123` `open()` → `Path.open()`, 5 `RUF002` en-dashes in test docstrings.

**Remediation:**
- Factored `_reject(code, error)` helper in `firebase_auth.py` (PLR0911 threshold-bumped for that specific file via per-file-ignore; 7 well-documented error paths).
- Removed all dead `noqa` directives.
- Removed unused imports + empty TYPE_CHECKING blocks.
- Added `r"""` raw-string docstrings where backslashes present.
- Added `main()` docstrings to `scripts/*.py`.
- Switched `open()` → `Path.open()` in `seed_firestore.py`.
- Added `ERA001` + `RUF002` to `tests/**` per-file-ignores (Given/When/Then comments + en-dashes in test-plan references).

## Important findings (should-fix, Sprint 0) — all remediated

### 3. `rate_limit.py` 0% coverage ✅ FIXED (CR5)

Reviewer: either add a smoke test or omit from coverage scope. Going with the first option for parity with the other 4 middlewares.

**Remediation:** Added `tests/unit/middleware/test_rate_limit.py::test_stub_does_not_reject_requests` — 50 rapid requests through the stub middleware, all return 200.

### 4. `test_audit_log.py::test_correlation_id_present_on_401` partially tautological ✅ FIXED (via Risk 11 stronger guard)

Reviewer: assertion was "any entry has correlation_id" — could pass from a cross-test leak. Recommended tightening to match `entry.get("path") == "/protected"`.

**Remediation:** Rather than tighten Test 4.2, added a STRONGER Risk 11 regression guard at `tests/unit/runners/test_main.py::test_audit_log_is_outermost_after_create_app`. This asserts the middleware-stack ordering directly (not relying on log emissions). Both tests remain; the new one is the primary guard.

### 5. `FirebaseAuthMiddleware` bare `except Exception` swallows too much ✅ FIXED (CR6)

Reviewer: catch-all obscures network errors, JWKS fetch transients as generic 401 invalid_token.

**Remediation:** Narrowed to `except (ValueError, firebase_auth.CertificateFetchError)`. ValueError covers firebase-admin-python #766 (non-string / empty token). CertificateFetchError covers transient JWKS issues. Other exceptions now bubble up as bugs, not covered up as 401s.

### 6. `ShipmentImpact.deadline` typed as `str`, not `datetime` ✅ FIXED (CR3)

Reviewer: violates `models.md` §2 tz-aware rule. Firestore Timestamp round-tripping breaks with `str`.

**Remediation:** Changed to `datetime` with `noqa: TC003` runtime-needed import comment. Pydantic parses ISO-8601 on input, round-trips via `model_dump(mode="json")`. Test 1.6 continues to pass without change.

### 7. `hello_world/agent.py` empty placeholder ✅ FIXED (C6)

Not a review finding per se, but reviewer flagged that the `__init__.py` re-export comment mentioned §17 #9 (schemas) while acceptance criteria #3 + #17 need the real agent. C6 built the real `LlmAgent(model="gemini-2.5-flash", name="hello_world")` with co-located `prompts/hello_world.md` + runner shim + evalset.

## Medium-confidence observations — all remediated

### 8. `learned_priorities: dict[str, Any]` too loose ✅ FIXED (CR8)

**Remediation:** Tightened to `dict[str, float]` — the Impact agent reads these as numeric weights.

### 9. `get_firestore_client()` docstring vs behavior mismatch ✅ FIXED (CR9)

Reviewer: docstring claims to honor `FIRESTORE_EMULATOR_HOST`, but code doesn't set `os.environ` from the Settings field. A caller setting `settings.firestore_emulator_host` but not the env var would silently talk to prod.

**Remediation:** Before constructing the client, `get_firestore_client()` now exports `settings.firestore_emulator_host` to `os.environ["FIRESTORE_EMULATOR_HOST"]` if the env isn't already set. Behavior now matches the docstring.

### 10. `BaseHTTPMiddleware` deprecation ⏸ DEFERRED TO SPRINT 4

Already Zettel'd by me before the reviewer ran (`Supply-Chain-Zettel-BaseHTTPMiddleware-Risk`). Reviewer acknowledged. Sprint 4 refactors to pure ASGI before SSE lands.

## What the reviewer called out as done well

- **Strict TDD visibly followed.** Given/When/Then comment pattern in every test; schemas built against behavioral tests, not the other way.
- **Docstring discipline tight.** Required scopes (middleware, memory, runners) covered; optional ones (schemas, tests, utils) correctly silenced.
- **Import-linter contracts match `architecture-layers.md` verbatim** — 5 contracts, all kept throughout Phase C.
- **`Settings` uses pydantic-settings correctly** — `get_secret` lazy-imports `secretmanager`, exactly the pattern `observability.md` §9 requires.
- **Risk 11 regression guard exists** (and was strengthened per CR4).
- **`CompanyProfile.to_markdown()` + `render_learned_preferences()` separation** traces cleanly back to the vault-inconsistency Zettel — research→design fidelity visible.
- **`rate_limit.py` stub correctly preserves the middleware-stack shape** so Sprint 4 doesn't need to re-thread imports through `main.py`.

## Reviewer-flagged items deferred to Sprint 1+

- Naming consistency between `request.state.user_id` (our choice) and the "uid" term in vault docs — documented the convention in the `FirebaseAuthMiddleware` docstring; Sprint 1 Classifier tools will read from `request.state.user_id`.
- `check_revoked=True` — Sprint 4 privileged-route hardening.

## Reviewer sprint-gate assessment

> "Net: #14 is a hard fail right now" — has been since fixed (CR1). All other gate items either pass or wait on user-owned artifacts (pre-commit / CI / `.env.template`).

## Human reviewer notes

The AI reviewer was asked to skip items I had already Zettel'd (BaseHTTPMiddleware, `check_revoked`) and focus on net-new findings — it did both correctly. The confidence-filtered output (only high-priority items) made this review tractable at the 27-file diff size; a non-filtered pass would have generated noise about docstring placement, import grouping, and line length that adds no signal over the existing ruff/mypy baseline.

For Sprint 1 reviews: same pattern. Specify the rule files + ADR scope up front; list items already Zettel'd; demand high-confidence findings only.

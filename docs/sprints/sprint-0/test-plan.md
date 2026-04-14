---
title: "Sprint 0 Test Plan v2"
type: deep-dive
domains: [supply-chain, testing, sdlc]
last_updated: 2026-04-14
version: v2
supersedes: "inline in prd-v1-archived.md (Area 1 of that test-plan)"
status: active
confidence: high
sources:
  - "[[Supply-Chain-Sprint-Plan-Spiral-SDLC]]"
  - "./prd.md §8 (schema signatures)"
---

# Sprint 0 Test Plan (v2)

> Given/When/Then test cases for Sprint 0 Foundation. Written **test-first per ADR-005 (Strict TDD)**: each test MUST be written and run to confirm failure before any implementation code.

## Changes from v1

- Import paths rewritten to `supply_chain_triage.modules.triage.models.*` (modular layout).
- **Test 1.10b added** — `render_learned_preferences` emits `## Learned Preferences` header.
- **Test 1.12b added** — `CompanyProfile.to_markdown()` emits `## Business Context` with `avg_daily_revenue_inr`.
- **Total test count: 30 → 32.**
- Emulator fixture updated per `.claude/rules/testing.md` §5 (session-scoped, `FIRESTORE_EMULATOR_HOST` + `FIREBASE_AUTH_EMULATOR_HOST`, per-test DELETE teardown).
- Coverage target clause made explicit about Tier 1 advisory window.
- Evalset guidance noted: **leaf agents only, NOT Coordinators** (ADK bug #3434, `.claude/rules/testing.md` §3).

## Test conventions

- Framework: `pytest >= 7.3.2` + `pytest-asyncio >= 0.21.0` (Resolved Decision #6)
- Python: **3.13** (Resolved Decision #1)
- Async tests: `@pytest.mark.asyncio` (auto mode in pyproject — don't annotate manually)
- Layout: `tests/unit/`, `tests/integration/`, `tests/e2e/`
- Fixtures: `tests/conftest.py` at session level; per-area conftest allowed
- Naming: `tests/unit/<area>/test_<subject>.py::test_<behavior>`
- Auth mocking: `firebase_admin.auth.verify_id_token` is mocked via `pytest-mock` monkeypatching. Unit tests never hit real Firebase.
- Coverage: advisory through Tier 1 (2026-04-24). Reports via `--cov-report=term-missing --cov-report=xml`. Hardens to 90% pure-logic at Tier 2 boundary.
- Evalsets (NOT pytest): `evals/<leaf_agent>/*.evalset.json`, run by `adk eval`. **Do not put evalsets on Coordinator agents** — known ADK bug (adk-python#3434).

---

## Area 1: Pydantic Schema Tests (Unit) — 14 tests

All schemas import from `supply_chain_triage.modules.triage.models`.

### Test 1.1: ExceptionEvent round-trips
- **Given** a valid ExceptionEvent dict matching the vault Coordinator schema
- **When** parsed with `ExceptionEvent.model_validate()` then serialized with `.model_dump(mode="json")`
- **Then** the round-tripped dict equals the original; no validation errors

### Test 1.2: ExceptionEvent rejects invalid source_channel
- **Given** dict with `source_channel="carrier_pigeon"` (not in Literal)
- **When** `ExceptionEvent.model_validate()` called
- **Then** `ValidationError` raised; message names `source_channel`

### Test 1.3: ClassificationResult round-trips with confidence 0–1
- **Given** `ClassificationResult` with `confidence=0.85`
- **When** serialized + reparsed
- **Then** `confidence` preserved exactly

### Test 1.4: ClassificationResult rejects confidence > 1.0
- **Given** dict with `confidence=1.5`
- **When** parsed
- **Then** `ValidationError` on `confidence`

### Test 1.5: ImpactResult handles empty affected_shipments
- **Given** `ImpactResult` with `affected_shipments=[]` and totals of 0
- **When** parsed
- **Then** no error; `has_reputation_risks == False`

### Test 1.6: ShipmentImpact requires deadline
- **Given** `ShipmentImpact` without `deadline`
- **When** parsed
- **Then** `ValidationError` naming `deadline`

### Test 1.7: TriageResult status enum enforced
- **Given** `TriageResult` with `status="totally_fine"`
- **When** parsed
- **Then** `ValidationError`; acceptable: `complete | partial | escalated_to_human | escalated_to_human_safety`

### Test 1.8: TriageResult allows impact=None (Rule F skip)
- **Given** `TriageResult` with `impact=None` and `status="complete"`
- **When** parsed
- **Then** succeeds (Optional field — `None` reflects Rule F skip per Coordinator spec)

### Test 1.9: UserContext requires preferred_language
- **Given** `UserContext` dict missing `preferred_language`
- **When** parsed
- **Then** `ValidationError`

### Test 1.10: UserContext.to_markdown renders 3 sections
- **Given** a populated `UserContext`
- **When** `.to_markdown()` called
- **Then** output contains **`## Identity`**, **`## Volume & Workload`**, **`## Communication Preferences`** section headers
- **Note:** per `docs/research/zettel-vault-coordinator-inconsistency.md`, this helper intentionally covers only the `<user_context>` XML block's 3 sections. Business Context → §1.12b; Learned Preferences → §1.10b.

### Test 1.10b (NEW): render_learned_preferences emits `## Learned Preferences`
- **Given** a `UserContext` with `override_patterns=["prefer-Trina-Logistics", "skip-carrier-callback-after-7pm"]` and `learned_priorities={"value_weight": 0.5}`
- **When** `render_learned_preferences(user_context)` called
- **Then** output contains **`## Learned Preferences`** header AND includes the override pattern strings AND includes a reference to the learned priorities dict contents
- **Why:** feeds the Coordinator's `<learned_behaviors>` XML block. Rule F severity calibration and override learning depend on this.

### Test 1.11: CompanyProfile requires avg_daily_revenue_inr
- **Given** `CompanyProfile` without `avg_daily_revenue_inr`
- **When** parsed
- **Then** `ValidationError` (required per Classifier Severity Validator Rule 3 — vault Classifier spec lines 200-209)

### Test 1.12: CompanyProfile round-trips with customer_portfolio
- **Given** `CompanyProfile` with nested `customer_portfolio` dict
- **When** round-tripped
- **Then** nested structure preserved

### Test 1.12b (NEW): CompanyProfile.to_markdown emits `## Business Context` with avg_daily_revenue_inr
- **Given** a populated `CompanyProfile` with `name="NimbleFreight"`, `num_trucks=22`, `avg_daily_revenue_inr=180_000`
- **When** `.to_markdown()` called
- **Then** output contains **`## Business Context`** header AND includes `NimbleFreight`, `22 trucks`, and **`₹180000`** (or `180,000`/`180_000` — any human-readable form of the value)
- **Why:** feeds the Coordinator's `<company_context>` XML block. Classifier Rule 3 (5% revenue threshold) only fires if `avg_daily_revenue_inr` is visible in the injected context.

---

## Area 2: Firebase Auth Middleware Tests (Unit) — 6 tests

Uses `firebase-admin` SDK (Resolved Decision #4). `firebase_admin.auth.verify_id_token` is mocked via `pytest-mock` monkeypatching — no real Firebase round-trip in unit tests.

### Test 2.1: Valid Firebase JWT passes
- **Given** FastAPI test client; mocked `verify_id_token` returning `{"uid": "u1", "email": "a@b.c", "company_id": "comp_1"}`
- **When** `GET /protected` with `Authorization: Bearer <token>`
- **Then** status 200; `request.state.user_id == "u1"`; `request.state.company_id == "comp_1"`

### Test 2.2: Expired JWT rejected
- **Given** mocked `verify_id_token` raises `firebase_admin.auth.ExpiredIdTokenError`
- **When** `GET /protected`
- **Then** status 401; body `{"error": "token_expired"}`

### Test 2.3: Tampered signature rejected
- **Given** mocked `verify_id_token` raises `firebase_admin.auth.InvalidIdTokenError`
- **When** `GET /protected`
- **Then** status 401; body `{"error": "invalid_signature"}`

### Test 2.4: Missing Authorization header rejected
- **Given** no `Authorization` header
- **When** `GET /protected`
- **Then** status 401; body `{"error": "missing_credentials"}`

### Test 2.5: Token without company_id custom claim rejected (multi-tenant guard)
- **Given** mocked `verify_id_token` returning `{"uid": "u1"}` (no `company_id`)
- **When** `GET /protected`
- **Then** status 403; body `{"error": "missing_company_claim"}`
- **Positive counterpart:** see Test 9.2 — tests the full flow against the Firebase Auth emulator with `scripts/set_custom_claims.py` having set a valid `company_id` beforehand.

### Test 2.6: Generic ValueError from verify_id_token yields 401 (catch-all coverage)
- **Given** mocked `verify_id_token` raises `ValueError("boom")`
- **When** `GET /protected` with Bearer token
- **Then** status 401; body `{"error": "invalid_token"}`
- **Note:** covers the catch-all `except Exception` branch; eliminates the need for `# pragma: no cover`

---

## Area 3: Input Sanitization Tests (Unit) — 3 tests

### Test 3.1: XSS script tag stripped
- **Given** input `<script>alert('x')</script>Hello`
- **When** `sanitize(input)` called
- **Then** output is `Hello` (or script tags HTML-escaped)

### Test 3.2: Control characters stripped
- **Given** input containing `\x00\x01\x02` bytes
- **When** `sanitize(input)` called
- **Then** output contains no bytes with ordinal < 32 except `\n \r \t`

### Test 3.3: Unicode preserved (Hindi/Hinglish)
- **Given** input `"गाड़ी खराब हो गई"` (vehicle broken in Hindi)
- **When** `sanitize(input)` called
- **Then** output equals input byte-for-byte (must NOT strip valid unicode — critical for India market)

---

## Area 4: Audit Log Tests (Unit) — 2 tests

### Test 4.1: Correlation ID propagates through log call
- **Given** `audit_log.info("action_X", correlation_id="abc-123", user_id="user_1")`
- **When** log sink captures output
- **Then** captured JSON contains `{"event": "action_X", "correlation_id": "abc-123", "user_id": "user_1", "timestamp": "<iso>"}`

### Test 4.2: Correlation ID logged on auth 401 (middleware ordering regression guard)
- **Given** full FastAPI app with canonical middleware stack (`AuditLog` outermost → `FirebaseAuth` → `InputSanitization` → `CORS`), captured structlog sink, and a request rejected by `FirebaseAuthMiddleware` (no `Authorization` header)
- **When** `GET /protected`
- **Then** response is 401 AND captured audit log for that request contains non-empty `correlation_id` — proving `AuditLogMiddleware` wrapped the auth-failure response
- **Regression guard:** catches anyone reordering `add_middleware` calls in `create_app()` such that `FirebaseAuth` becomes outermost (short-circuiting audit).

---

## Area 5: ADK Hello World Agent Test (Agent Evaluator) — 1 test

### Test 5.1: hello_world_agent responds to greeting
- **Given** `hello_world_agent = LlmAgent(model="gemini-2.5-flash", name="hello_world")` and real `GEMINI_API_KEY` from Secret Manager
- **When** `AgentEvaluator.evaluate(agent=hello_world_agent, input="hello")` runs
- **Then** response is non-empty string; no error markers

> **Marker:** `@pytest.mark.integration`. Skipped in fast CI unless `GEMINI_API_KEY` available.

> **Note on evalsets:** Sprint 0 also ships `evals/hello_world/greeting.evalset.json` for `adk eval`. Evalsets are **separate** from pytest. hello_world is a leaf agent — evalsets allowed. Coordinator agents do NOT get evalsets (ADK bug #3434).

---

## Area 6: Firestore Emulator Integration Test — 1 test

### Test 6.1: Write and read round-trip via emulator
- **Given** Firestore emulator running on `localhost:8080` (started via session-scoped fixture per `.claude/rules/testing.md` §5)
- **When** test writes a `CompanyProfile` doc to `companies/test_co_001` then reads it back
- **Then** read document equals written document
- **Fixture**: `firestore_emulator` autouse session fixture sets `FIRESTORE_EMULATOR_HOST=localhost:8080` **BEFORE** any Firestore client import. Per-test teardown: `DELETE http://localhost:8080/emulator/v1/projects/sct-test/databases/(default)/documents` to clear state.
- **Marker:** `@pytest.mark.integration`

---

## Area 7: CORS Tests (Unit) — 2 tests

### Test 7.1: Allowed origin passes preflight
- **Given** FastAPI app with CORS allowlist `["http://localhost:3000"]`
- **When** OPTIONS with `Origin: http://localhost:3000`
- **Then** response includes `Access-Control-Allow-Origin: http://localhost:3000`

### Test 7.2: Disallowed origin blocked
- **Given** same app
- **When** OPTIONS with `Origin: http://evil.com`
- **Then** response does NOT include `Access-Control-Allow-Origin` (or explicit 403)

---

## Area 8: Pre-commit Meta Tests — 2 tests

### Test 8.1: Ruff fires on unformatted file
- **Given** staged file with double blank lines + unused import
- **When** `pre-commit run ruff --files bad.py`
- **Then** non-zero exit; stdout contains ruff findings

### Test 8.2: Bandit/gitleaks fires on hardcoded secret
- **Given** file containing `password = "hunter2"`
- **When** `pre-commit run bandit --files leaky.py` (or `gitleaks` equivalent)
- **Then** non-zero exit; output identifies the hardcoded password

> Verification-of-tooling tests. Run manually during Sprint 0 gate check. Not in regular CI.

---

## Area 9: Secret Manager + Custom Claims Integration — 2 tests

### Test 9.1: Secret fetched at runtime, not build time
- **Given** `GEMINI_API_KEY` stored in GCP Secret Manager as secret version
- **When** `get_secret("GEMINI_API_KEY")` called in running container (or locally with ADC)
- **Then** returns current secret value; value does NOT appear in Docker image layers (verify via `docker history --no-trunc`)
- **Marker:** `@pytest.mark.integration` + `@pytest.mark.slow`

### Test 9.2 (NEW — positive counterpart to Test 2.5): Valid company_id claim passes auth
- **Given** Firebase Auth emulator running, `scripts/set_custom_claims.py --uid test_u_1 --company-id comp_1` executed, client fetches fresh ID token, FastAPI app wired with `FIREBASE_AUTH_EMULATOR_HOST=localhost:9099`
- **When** `GET /protected` with that Bearer token
- **Then** status 200; `request.state.company_id == "comp_1"`
- **Marker:** `@pytest.mark.integration`
- **Why:** proves the `set_custom_claims.py` → token refresh → middleware chain works end-to-end. Test 2.5 is the negative case; this is the positive case.

---

## Test Execution Commands

```bash
# Run all fast tests
uv run pytest -m "not integration"

# Run all tests (unit + integration; requires emulators running)
uv run pytest

# Run with coverage (advisory through Tier 1 — no fail gate)
uv run pytest --cov

# Run a single test
uv run pytest tests/unit/schemas/test_exception_event.py::test_round_trips -v

# Pre-commit check
pre-commit run --all-files

# Evalset (separate from pytest)
adk eval src/supply_chain_triage/modules/triage/agents/hello_world evals/hello_world/greeting.evalset.json
```

---

## Coverage target

- **Through Tier 1 (2026-04-24)**: **ADVISORY**. `--cov-report=term-missing --cov-report=xml`; no `--cov-fail-under`.
- **From Tier 2**: gate at 90% on pure-logic paths (`core/`, `utils/`, `middleware/`, `modules/triage/{models,tools,guardrails,memory}/`). Agents validated by evalsets, not coverage.
- **Critical paths** (middleware, sanitizer, schemas): target **≥95%** once gating.
- **Excluded always**: `main.py`, all `__init__.py` (already in `[tool.coverage.run] omit`).

---

## Test Budget

| Area | Tests |
|------|-------|
| Pydantic schemas | 14 (12 from v1 + Test 1.10b + Test 1.12b) |
| Firebase Auth middleware | 6 |
| Input sanitization | 3 |
| Audit log | 2 |
| ADK hello_world | 1 |
| Firestore emulator | 1 |
| CORS | 2 |
| Pre-commit meta | 2 |
| Secret Manager + custom claims | 2 (9.1 + NEW 9.2) |
| **Total** | **33** |

> **Note:** PRD §17 gate says "≥ 32 tests" — that target includes the net-new schema tests (1.10b, 1.12b) and the pre-existing 30 from v1. Test 9.2 (custom claims positive-case) is additive; actual test count is **33**. If Test 9.2 requires firebase-admin emulator setup that's not ready by Phase C close, defer Test 9.2 to Sprint 4 and document as a scope carryover (stays at 32).

---

## Exit Criteria

All tests green. Pre-commit passes on clean repo. CI workflow + security workflow green on main. `deploy.yml` stub exits 0 with TODO message. Evalset `adk eval evals/hello_world/greeting.evalset.json` green.

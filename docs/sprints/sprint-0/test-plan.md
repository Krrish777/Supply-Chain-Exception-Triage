---
title: "Sprint 0 Test Plan"
type: deep-dive
domains: [supply-chain, testing, sdlc]
last_updated: 2026-04-10
status: active
confidence: high
sources: ["[[Supply-Chain-Sprint-Plan-Spiral-SDLC]]"]
---

# Sprint 0 Test Plan

> Given/When/Then test cases for Sprint 0 Foundation. Written test-first per ADR-005 (Strict TDD). Each test must be written and **run to confirm it fails** before any implementation code.

## Test Conventions

- Framework: `pytest 7.3.2+` + `pytest-asyncio 0.21.0+` (Resolved Decision #6)
- Python: **3.13** (Resolved Decision #1)
- Async tests: `@pytest.mark.asyncio` (auto mode in pyproject)
- Layout: `tests/unit/`, `tests/integration/`, `tests/e2e/`
- Fixtures: `conftest.py` at each layer
- Naming: `tests/unit/<area>/test_<subject>.py::test_<behavior>`
- Auth mocking: `firebase_admin.auth.verify_id_token` is mocked via
  `pytest-mock` monkeypatching — unit tests never hit real Firebase.

---

## Area 1: Pydantic Schema Tests (Unit)

### Test 1.1: ExceptionEvent round-trips
- **Given** a valid ExceptionEvent dict matching [[Supply-Chain-Agent-Spec-Coordinator]] schema
- **When** parsed with `ExceptionEvent.model_validate()` then serialized with `.model_dump(mode="json")`
- **Then** the round-tripped dict equals the original and no validation errors are raised

### Test 1.2: ExceptionEvent rejects invalid source_channel
- **Given** a dict with `source_channel="carrier_pigeon"` (not in Literal enum)
- **When** `ExceptionEvent.model_validate()` is called
- **Then** `ValidationError` is raised with a message naming `source_channel`

### Test 1.3: ClassificationResult round-trips with confidence 0–1
- **Given** a valid ClassificationResult with `confidence=0.85`
- **When** serialized and reparsed
- **Then** confidence value is preserved exactly

### Test 1.4: ClassificationResult rejects confidence > 1.0
- **Given** a dict with `confidence=1.5`
- **When** parsed
- **Then** ValidationError on `confidence` field

### Test 1.5: ImpactResult handles empty affected_shipments
- **Given** ImpactResult with `affected_shipments=[]` and totals of 0
- **When** parsed
- **Then** no error and `has_reputation_risks == False`

### Test 1.6: ShipmentImpact requires deadline fields
- **Given** ShipmentImpact without `deadline`
- **When** parsed
- **Then** ValidationError naming `deadline`

### Test 1.7: TriageResult status enum enforced
- **Given** TriageResult with `status="totally_fine"`
- **When** parsed
- **Then** ValidationError; acceptable values are `complete | partial | escalated_to_human | escalated_to_human_safety`

### Test 1.8: TriageResult allows impact=None (Rule F skip)
- **Given** TriageResult with `impact=None` and `status="complete"`
- **When** parsed
- **Then** succeeds (Optional field)

### Test 1.9: UserContext requires preferred_language
- **Given** UserContext dict missing `preferred_language`
- **When** parsed
- **Then** ValidationError

### Test 1.10: UserContext markdown rendering helper
- **Given** a populated UserContext
- **When** `.to_markdown()` is called
- **Then** output contains `## Identity`, `## Volume & Workload`, `## Communication Preferences` section headers

### Test 1.11: CompanyProfile requires avg_daily_revenue_inr
- **Given** CompanyProfile without `avg_daily_revenue_inr`
- **When** parsed
- **Then** ValidationError (this field is required per Classifier Rule 3)

### Test 1.12: CompanyProfile round-trips with customer_portfolio
- **Given** CompanyProfile with nested `customer_portfolio` dict
- **When** round-tripped
- **Then** nested structure preserved

---

## Area 2: Firebase Auth Middleware Tests (Unit)

> Uses `firebase-admin` SDK (Resolved Decision #4). `firebase_admin.auth.verify_id_token`
> is mocked via `pytest-mock` monkeypatching — no real Firebase round-trip in unit tests.

### Test 2.1: Valid Firebase JWT passes
- **Given** a FastAPI test client and a mocked `verify_id_token` returning `{"uid": "u1", "email": "a@b.c", "company_id": "comp_1"}`
- **When** GET `/protected` with `Authorization: Bearer <token>`
- **Then** response status is 200 and `request.state.user_id == "u1"` and `request.state.company_id == "comp_1"`

### Test 2.2: Expired JWT rejected
- **Given** mocked `verify_id_token` raises `firebase_admin.auth.ExpiredIdTokenError`
- **When** GET `/protected`
- **Then** response status is 401 with body `{"error": "token_expired"}`

### Test 2.3: Tampered signature rejected
- **Given** mocked `verify_id_token` raises `firebase_admin.auth.InvalidIdTokenError`
- **When** GET `/protected`
- **Then** response status is 401 with body `{"error": "invalid_signature"}`

### Test 2.4: Missing Authorization header rejected
- **Given** no `Authorization` header
- **When** GET `/protected`
- **Then** response status is 401 with body `{"error": "missing_credentials"}`

### Test 2.5: Token without `company_id` custom claim rejected (multi-tenant guard)
- **Given** mocked `verify_id_token` returning `{"uid": "u1"}` (no `company_id`)
- **When** GET `/protected`
- **Then** response status is 403 with body `{"error": "missing_company_claim"}`

### Test 2.6: Generic ValueError from verify_id_token yields 401 (catch-all coverage)
- **Given** mocked `verify_id_token` raises a plain `ValueError("boom")`
- **When** GET `/protected` with a Bearer token
- **Then** response status is 401 with body `{"error": "invalid_token"}`
- **Note**: this covers the catch-all `except Exception` branch in
  `firebase_auth.py`, ensuring no uncaught exception path exists and
  removing the need for a `# pragma: no cover` annotation.

---

## Area 3: Input Sanitization Tests (Unit)

### Test 3.1: XSS script tag stripped
- **Given** input string `<script>alert('x')</script>Hello`
- **When** `sanitize(input)` is called
- **Then** output is `Hello` (or script tags HTML-escaped)

### Test 3.2: Control characters stripped
- **Given** input containing `\x00\x01\x02` bytes
- **When** `sanitize(input)` is called
- **Then** output contains no bytes with ordinal < 32 except `\n \r \t`

### Test 3.3: Unicode preserved (Hindi/Hinglish)
- **Given** input `"गाड़ी खराब हो गई"` (vehicle broken in Hindi)
- **When** `sanitize(input)` is called
- **Then** output equals input byte-for-byte (must not strip valid unicode — critical for India market)

---

## Area 4: Audit Log Test (Unit)

### Test 4.1: Correlation ID propagates through log call
- **Given** `audit_log.info("action_X", correlation_id="abc-123", user_id="user_1")`
- **When** the log sink captures output
- **Then** captured JSON contains `{"event": "action_X", "correlation_id": "abc-123", "user_id": "user_1", "timestamp": "<iso>"}`

### Test 4.2: Correlation ID logged on auth 401 (middleware ordering regression guard)
- **Given** the full FastAPI app with the canonical middleware stack
  (`AuditLog` outermost → `FirebaseAuth` → `InputSanitization` → `CORS`),
  a captured structlog sink, and a request that will be rejected by
  `FirebaseAuthMiddleware` (no `Authorization` header)
- **When** GET `/protected`
- **Then** the response is 401 AND the captured audit log for that
  request contains a non-empty `correlation_id` field, proving the
  `AuditLogMiddleware` wrapped the auth failure response
- **Regression guard**: this test exists specifically to catch anyone
  re-ordering `add_middleware` calls in `main.py::create_app()` such
  that `FirebaseAuth` becomes outermost and short-circuits audit logging.

---

## Area 5: ADK Hello World Agent Test (Agent Evaluator)

### Test 5.1: hello_world_agent responds to greeting
- **Given** `hello_world_agent = LlmAgent(model="gemini-2.5-flash", name="hello_world")` and real `GEMINI_API_KEY` from Secret Manager
- **When** `AgentEvaluator.evaluate(agent=hello_world_agent, input="hello")` runs
- **Then** response is non-empty string and contains no error markers

> Note: This test hits real Gemini API. Mark `@pytest.mark.integration` and skip in CI unless `GEMINI_API_KEY` available as secret.

---

## Area 6: Firestore Emulator Integration Test

### Test 6.1: Write and read round-trip via emulator
- **Given** Firestore emulator running on `localhost:8080` (via `firebase emulators:start`)
- **When** a test writes a `CompanyProfile` doc to `companies/test_co_001` then reads it back
- **Then** read document equals written document
- **Fixture**: `firestore_emulator` autouse fixture sets `FIRESTORE_EMULATOR_HOST=localhost:8080`

---

## Area 7: CORS Tests (Unit)

### Test 7.1: Allowed origin passes preflight
- **Given** FastAPI app with CORS allowlist `["http://localhost:3000"]`
- **When** OPTIONS request with `Origin: http://localhost:3000`
- **Then** response includes `Access-Control-Allow-Origin: http://localhost:3000` header

### Test 7.2: Disallowed origin blocked
- **Given** same app
- **When** OPTIONS request with `Origin: http://evil.com`
- **Then** response does NOT include `Access-Control-Allow-Origin` header (or explicitly blocks)

---

## Area 8: Pre-commit Meta Tests

### Test 8.1: Ruff fires on unformatted file
- **Given** a staged file with obvious style violations (double blank lines, unused import)
- **When** `pre-commit run ruff --files bad.py` is invoked
- **Then** exit code is non-zero and stdout contains `ruff` findings

### Test 8.2: Bandit fires on hardcoded secret
- **Given** a file containing `password = "hunter2"` literal
- **When** `pre-commit run bandit --files leaky.py` is invoked
- **Then** exit code is non-zero and stdout contains `B105` (hardcoded password)

> These are verification-of-tooling tests, run manually during Sprint 0 gate check, not in regular CI.

---

## Area 9: Secret Manager Runtime Fetch (Integration)

### Test 9.1: Secret fetched at runtime, not build time
- **Given** `GEMINI_API_KEY` stored in GCP Secret Manager as secret version
- **When** `get_secret("GEMINI_API_KEY")` is called in a running container (or locally with ADC)
- **Then** returns the current secret value, and the value does NOT appear in Docker image layers

> Verify by building image with `--no-cache`, grepping `docker history --no-trunc` for the secret string (should be absent).

---

## Test Execution Commands

```bash
# Run all unit tests (fast)
make test

# Run with coverage
make coverage

# Run only integration tests (requires emulator + Gemini key)
pytest tests/integration/ -v --slow

# Run a single test
pytest tests/unit/schemas/test_exception_event.py::test_round_trips -v

# Pre-commit check
pre-commit run --all-files
```

## Coverage Target

- **Unit test coverage:** ≥ 80% on `src/`
- **Critical paths** (middleware, sanitizer, schemas): ≥ 95%
- **Excluded**: `main.py` (bootstrapping), `__init__.py` modules

## Test Budget Update

| Area | Tests |
|------|-------|
| Pydantic schemas | 12 |
| Firebase Auth middleware | 6 (tests 2.1–2.5 + test 2.6 generic-ValueError→401 catch-all coverage) |
| Input sanitization | 3 |
| Audit log | 2 (test 4.1 log shape + test 4.2 correlation_id on 401 regression guard) |
| ADK hello_world | 1 |
| Firestore emulator | 1 |
| CORS | 2 |
| Pre-commit meta | 2 |
| Secret Manager runtime fetch | 1 |
| **Total** | **30 tests** |

## Exit Criteria

All 30 tests green. Pre-commit passes on clean repo. CI workflow + security workflow green on main branch. `deploy.yml` stub exits 0 with TODO message.

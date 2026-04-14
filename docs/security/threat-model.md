# Threat Model — Sprint 0

> STRIDE analysis scoped to Sprint 0's attack surface. Expanded at Sprint 4 when the real API layer (`/triage/stream`) ships.

## Scope

Sprint 0 exposes:
- A FastAPI `create_app()` factory with `/health` (public) + middleware stack (not yet wired to routes).
- The ADK `hello_world` agent (invokable via `adk web` locally, not exposed over HTTP yet).
- Firestore emulator integration (local only; not deployed).
- GCP Secret Manager fetch path via `core.config.get_secret()`.

**Not in Sprint 0's threat model** (deferred to the sprint that ships each surface):
- `/triage/stream` SSE endpoint — Sprint 4 re-threat.
- React frontend CSP, clickjacking, CSRF — Sprint 5.
- Real Supermemory + live Gemini traffic — Sprint 4.

## Assets

| Asset | Sensitivity | Where |
|---|---|---|
| Firebase ID tokens (client-side) | High | HTTP Authorization header |
| `company_id` custom claim | High | Token payload |
| Gemini API key | Critical | Secret Manager + `.env` |
| Supermemory API key | Critical | Secret Manager |
| Firestore documents (shipments, customers, exceptions) | High (business-sensitive) | Firestore |
| Audit logs (correlation_id, user_id, company_id) | Medium | Cloud Logging |

## STRIDE analysis

### Spoofing

**Threat:** Attacker presents a forged Firebase ID token.

- **Mitigation:** `FirebaseAuthMiddleware.dispatch` calls `firebase_admin.auth.verify_id_token()` on every non-public request. Verifies signature against Firebase's public key set. `ExpiredIdTokenError` / `InvalidIdTokenError` / generic `ValueError` all short-circuit to 401.
- **Residual risk:** `FIREBASE_AUTH_EMULATOR_HOST` env var makes the SDK accept forged tokens. Documented ban in `.claude/rules/testing.md` §6 + `security.md` §9.
- **Gap for Sprint 4:** `check_revoked=True` is not currently passed — revoked tokens are valid until expiry (up to 1 hour). Flagged in vault Zettel `Supply-Chain-Zettel-Firebase-Admin-Verify-Token`.

### Tampering

**Threat:** Attacker modifies request data or response bodies.

- **Mitigation (requests):** TLS terminates at Cloud Run (Sprint 5). `InputSanitizationMiddleware` strips XSS + control chars before handlers read body (real body rewriting lands Sprint 4; Sprint 0 ships the shape).
- **Mitigation (responses):** Sprint 0 has no mutations; all responses are constructed by our code. No response-tampering surface.
- **Mitigation (at-rest):** Firestore multi-tenant rules (`infra/firestore.rules`) enforce `company_id == resource.data.company_id` on every write. Direct-from-client mutations are impossible without a matching claim.

### Repudiation

**Threat:** Action taken without audit trail; attacker denies doing it.

- **Mitigation:** `AuditLogMiddleware` is the OUTERMOST middleware (Risk 11 guard). Every request — including 401s and 403s — gets a `correlation_id` + structured JSON audit record. Test 4.2 + the stack-ordering test in `tests/unit/runners/test_main.py` are the regression guards.
- **Gap:** Sprint 0 audit logs are structlog-emitted to stdout; Cloud Logging retention is not yet configured. Sprint 5 deployment ticket.

### Information disclosure

**Threat:** PII leaked via logs, error responses, or the agent itself.

- **Mitigation (logs):** `security.md` §7 mandates a structlog `_drop_pii` processor. Sprint 0 ships the rule; implementation lives in the Logger workstream (post-C10, pre-Phase D) per plan file.
- **Mitigation (agent):** Gemini prompts / responses are never logged. `.claude/rules/observability.md` §5 anti-pattern.
- **Mitigation (error responses):** Middleware 401/403 responses return only an error code (e.g. `{"error": "missing_company_claim"}`) — never echo back the token, claim contents, or stack trace.
- **Gap:** `install_rich_traceback(show_locals=True)` in dev shows local variables in tracebacks (potential PII leak). Off when `LOG_LEVEL != "DEBUG"`. Documented in Logger workstream.

### Denial of service

**Threat:** Abuse vectors exhaust Gemini budget or Firestore quota.

- **Mitigation (Sprint 0):** Stub only. `RateLimitMiddleware` is a pass-through (`TODO(sprint-4)`).
- **Mitigation (Sprint 4):** `slowapi` with distributed backend (Memorystore Redis). Per-uid + per-IP limits; Cloud Armor for coarse volumetric. See `.claude/rules/security.md` §4.
- **Residual risk through Sprint 4:** Single abusive user can drain Gemini budget. Mitigated operationally via GCP budget alerts at 50/90/100% (`observability.md` §6) — not prevented.

### Elevation of privilege

**Threat:** User reads/writes data of another tenant.

- **Mitigation (defense-in-depth):**
  1. `FirebaseAuthMiddleware` rejects tokens without `company_id` (403, `missing_company_claim`).
  2. Firestore rules (`infra/firestore.rules`) enforce `request.auth.token.company_id == resource.data.company_id` on every read/write.
  3. `MemoryProvider` contract mandates `company_id` as required positional arg (Risk 12 defense — cross-tenant Supermemory leak).
  4. `FakeSupermemoryClient` asserts `company_id` on every call so tests catch missing scoping immediately.

## Sprint-specific threats

| Sprint | Threat | Mitigation |
|---|---|---|
| 0 | Placement-hook bypass via direct git write | Pre-commit hooks catch on commit; CI re-runs the placement check |
| 0 | Secrets committed to git | Pre-commit `gitleaks` + `detect-secrets` baseline |
| 1 | Classifier prompt-injection via `raw_content` | Escape `<` / `>` in XML-block injection (Coordinator Sprint 3) |
| 2 | Impact agent over-weights reputation for gaming | LLM weight reasoning visible in `impact_weights_used`; human review loop |
| 4 | SSE event ordering exploited for confusion UX | Emit events in strict order; client validates monotonic event sequence |
| 5 | Deploy uses long-lived service account JSON | Workload Identity only; rotate keys every 30 days |

## Next review

- **Sprint 4** — re-threat when `/triage/stream` ships. Focus: streaming abuse, SSE backpressure, rate-limit bypass.
- **Sprint 5** — re-threat when React frontend + Cloud Run deploy lands. Focus: CSP, clickjacking, deploy-time secret leakage.

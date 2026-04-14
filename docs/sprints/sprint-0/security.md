---
title: "Sprint 0 Security Review"
type: deep-dive
domains: [supply-chain, security, sdlc]
last_updated: 2026-04-14
status: active
---

# Sprint 0 Security Review

> OWASP API Top 10 instance scoped to Sprint 0's attack surface + Sprint 0-specific hardening notes.

## Surface shipped this sprint

- FastAPI `create_app()` factory with canonical middleware stack + `/health` endpoint.
- ADK `hello_world` agent (invokable via `adk web`, not yet HTTP-exposed).
- Firestore emulator config (local only; not deployed).
- GCP Secret Manager fetch path via `core.config.get_secret()`.
- Multi-tenant custom-claim enforcement in `FirebaseAuthMiddleware` + `scripts/set_custom_claims.py`.

## OWASP API Top 10 — coverage as of Sprint 0 close

| # | Category | Status |
|---|---|---|
| API1 Broken Object-Level Authorization | ✅ addressed | `FirebaseAuthMiddleware` rejects tokens without `company_id` (403). `infra/firestore.rules` filters every read/write on `company_id`. `MemoryProvider` requires `company_id` positionally (Risk 12 mitigation). `FakeSupermemoryClient` asserts it in tests. |
| API2 Broken Authentication | ✅ addressed, one known gap | Firebase Admin SDK `verify_id_token` on every non-public request. 7 auth unit tests. **Gap:** `check_revoked=True` not yet passed (vault Zettel `Supply-Chain-Zettel-Firebase-Admin-Verify-Token`). Sprint 4 hardening. |
| API3 Broken Object Property-Level Authorization | ✅ addressed | Pydantic `extra="forbid"` on all schemas (input + output). Unknown fields raise ValidationError. |
| API4 Unrestricted Resource Consumption | ⏸ deferred (Sprint 4) | `RateLimitMiddleware` is a pass-through stub. Real enforcement (slowapi + Memorystore Redis) Sprint 4. Cloud Armor at deploy (Sprint 5). |
| API5 Broken Function-Level Authorization | ⏸ deferred (Sprint 4) | No privileged routes yet. Tier-gated routes land with `require_tier(N)` dependency factory per `.claude/rules/security.md` §3. |
| API6 Unrestricted Access to Sensitive Business Flows | ⏸ deferred (Sprint 4) | No business flows exposed yet. `/triage/stream` rate limits + per-agent cost caps land Sprint 4. |
| API7 Server-Side Request Forgery | ✅ addressed | No outbound requests to user-controlled URLs in Sprint 0. When Impact Agent (Sprint 2) adds external lookups, URLs are from Firestore seed data — not user input. |
| API8 Security Misconfiguration | ✅ addressed | CORS allowlist rejects wildcards at startup. Least-privilege IAM (dev SA: `secretmanager.secretAccessor` + `datastore.user`). Secret Manager runtime fetch (no env-baked secrets). `uv.lock` committed + `uv sync --locked` in CI (per deployment.md pattern). |
| API9 Improper Inventory Management | ⏸ deferred (Sprint 4) | OpenAPI auto-generated. Versioning (`/v1/...`) lands Tier 3 frontend. |
| API10 Unsafe Consumption of APIs | ✅ addressed | Every external response (Gemini, Supermemory, Firestore) parses through Pydantic schemas. No raw dicts cross the boundary — per `.claude/rules/api-routes.md` + `.claude/rules/tools.md`. |

## Sprint 0-specific hardening — status

| Control | State | Notes |
|---|---|---|
| `bcrypt` + `passlib` banned (ruff TID251) | ✅ | Firebase owns password hashing |
| `FIREBASE_AUTH_EMULATOR_HOST` ban outside dev | ✅ | Documented in `.claude/rules/testing.md` §6; pending pydantic-settings validator (Sprint 4) |
| Secret Manager runtime fetch (not module-import) | ✅ | `get_secret()` does lazy import + caches in-process; never reads at import |
| PII-safe structured logging | ✅ | `_drop_pii` processor in `utils/logging.py` strips `prompt, response, document, email, phone, raw_content, english_translation, original_language, password, api_key, token` before any handler sees them |
| Audit log on every request (incl. 401/403) | ✅ | `AuditLogMiddleware` outermost; Risk 11 regression guard at `tests/unit/runners/test_main.py::test_audit_log_is_outermost_after_create_app` |
| Multi-tenant isolation via custom claims | ✅ | Firebase custom claim `company_id` required; `scripts/set_custom_claims.py` sets it via Admin SDK |
| Firestore rules deny-all default | ✅ | `infra/firestore.rules` explicit catch-all `allow read, write: if false;` |
| Pre-commit `gitleaks` + `detect-secrets` | ⏳ user-owned | Hooks run once `.pre-commit-config.yaml` is populated |
| CI `bandit` + `safety` + `pip-audit` | ⏳ user-owned | Workflow in `.github/workflows/security.yml` |

## Sprint 0 threat model

Full STRIDE analysis: `docs/security/threat-model.md`. Summary here:

- **Spoofing** — Firebase Admin SDK verify_id_token. Residual: `check_revoked=True` gap (Sprint 4).
- **Tampering** — TLS at Cloud Run boundary (Sprint 5). Firestore rules enforce `company_id` match on write.
- **Repudiation** — `AuditLogMiddleware` outermost; every request has a `correlation_id` in the audit log.
- **Information disclosure** — PII drop processor. `install_rich_traceback(show_locals=True)` only at `LOG_LEVEL=DEBUG`, and bounded via `locals_max_string=80, locals_max_length=10`.
- **Denial of service** — stub only; Sprint 4 enforcement.
- **Elevation of privilege** — defense in depth via Firebase custom claim → middleware check → Firestore rules → MemoryProvider required-positional `company_id`.

## Known gaps flagged for future sprints

From vault Zettels saved to `C:\Users\777kr\Desktop\Obsidian-Notes-Vault\10 - Deep Dives\Supply-Chain\`:

- **`Supply-Chain-Zettel-BaseHTTPMiddleware-Risk`** — Starlette's `BaseHTTPMiddleware` is slated for deprecation and has known streaming-response bugs. All 5 Sprint 0 middleware use it. Refactor to pure ASGI before Sprint 4 SSE work.
- **`Supply-Chain-Zettel-Firebase-Admin-Verify-Token`** — `check_revoked=True` not currently passed. Revoked tokens valid until expiry. Sprint 4 hardening.
- **`Supply-Chain-Zettel-CloudRun-JSON-Log-Correlation`** — Cloud Run auto-correlation needs `logging.googleapis.com/trace` + `spanId` in JSON. Our logger emits `request_id` but not these yet. Adds OTel processor in Sprint 1+ when instrumentation lands.
- **`Supply-Chain-Zettel-Structlog-Async-Contextvars`** — FastAPI sync/async hybrid has subtle contextvar propagation gotchas. Canonical fix documented + implemented in `AuditLogMiddleware` (`bind_contextvars` + fallback `request_id_var`).

## Sprint 4 carry-over (security-specific)

- `check_revoked=True` on privileged routes
- `RateLimitMiddleware` real enforcement (slowapi + Redis backend)
- `InputSanitizationMiddleware` body rewriting (stub in Sprint 0)
- `SecurityHeaders` middleware (CSP, HSTS, X-Frame-Options) per `.claude/rules/security.md` §5
- Pydantic-settings validator for `FIREBASE_AUTH_EMULATOR_HOST` (ENV != "dev" → ValueError)
- Pydantic-settings validator for placeholder secrets
- Email-enumeration protection on `/auth/reset` when that endpoint lands

# Security Policy

## Supported versions

This project is under active development (Sprint 0 through Tier 3). Only the latest `main` branch receives security updates.

| Version | Supported |
|---|---|
| `main` (latest) | ✅ |
| Anything older | ❌ |

## Reporting a vulnerability

If you discover a security vulnerability:

1. **Do NOT open a public GitHub issue.**
2. Email the maintainer directly (address in `pyproject.toml` `[project].authors`).
3. Include: affected version/commit, reproduction steps, impact assessment, and any suggested remediation.
4. You should receive acknowledgement within 72 hours.

We follow responsible disclosure: give us reasonable time to patch before publishing details.

## Security non-negotiables

Enforced via code, lint, and policy:

- **Firebase Auth owns password hashing, JWT signing + verification, token expiry, token revocation.** See `.claude/rules/security.md` §1.
- **No custom password hashing.** `bcrypt` and `passlib` are banned project-wide via ruff `TID251`.
- **No secrets in code.** All secrets resolve through `core.config.get_secret()` → GCP Secret Manager (prod) or `.env` (local dev). Never hard-coded, never logged, never returned in error responses.
- **Multi-tenant isolation via Firebase custom claims.** Every document carries `company_id`; every read/write rule checks `request.auth.token.company_id == resource.data.company_id`. Claims are server-side-only (see `scripts/set_custom_claims.py`).
- **`FIREBASE_AUTH_EMULATOR_HOST` is forbidden in production environment.** The Firebase Admin SDK honors it unconditionally — setting it in Cloud Run accepts forged tokens.
- **Least-privilege IAM.** Dev service account has only `secretmanager.secretAccessor` + `datastore.user`. No `owner` or `editor`.
- **Audit logging on every request.** Structured JSON with `correlation_id`, `user_id`, `company_id`. AuditLogMiddleware is the outermost wrapper (Risk 11 regression guard at Test 4.2).
- **Dependency scanning on every CI run.** `bandit`, `safety`, `pip-audit`. Nightly cron catches new CVEs.
- **PII-safe logging.** An allowlist of loggable field names; banned fields (`prompt`, `response`, `email`, `phone`, `raw_content`, ...) are dropped by the structlog processor chain before the log record is formatted. See `.claude/rules/security.md` §7.
- **Pre-commit `gitleaks` + `detect-secrets`** catch accidental credential commits.

## Threat model

See [`docs/security/threat-model.md`](./docs/security/threat-model.md) for the STRIDE analysis.

## OWASP API Top 10 coverage

See [`docs/security/owasp-checklist.md`](./docs/security/owasp-checklist.md) for per-category status.

## Security scanning commitment

On every CI run, we run:
- `bandit -r src/` — Python security linter.
- `safety check` — known vulnerabilities in installed packages.
- `pip-audit` — OSV database cross-check.

On every nightly cron:
- The above, against `uv.lock`, as a drift detector.

## Responsible use

This software processes supply-chain exception data which may include business-sensitive information (shipment details, customer names, pricing, SLA terms). Anyone deploying it is responsible for:

- Running a DPIA if in the EU or equivalent jurisdictions.
- Configuring GCP log-bucket retention per local data-retention rules.
- Registering with Firebase App Check (recommended for production Tier 3+) to prevent abuse.

Sprint 0 operates on synthetic data only (see `scripts/seed/*.json` skeletons). Real customer data is out of scope until explicit onboarding in post-hackathon production work.

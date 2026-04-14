---
title: "Sprint 0 Risks — Pre-Mortem"
type: deep-dive
domains: [supply-chain, risk-management, sdlc]
last_updated: 2026-04-10
status: active
confidence: high
sources: ["[[Supply-Chain-Sprint-Plan-Spiral-SDLC]]"]
---

# Sprint 0 Risk Pre-Mortem

> **Frame**: It is Apr 13, 2026. Sprint 0 failed. Sprint 1 cannot start. The prototype submission on Apr 24 is now in serious jeopardy. **What happened?**
>
> Each risk below is a possible answer, ranked by probability × severity.

---

## Legend

- **Probability**: Low (< 20%) | Medium (20–50%) | High (> 50%)
- **Severity**: Low (annoyance) | Medium (delays sprint) | High (delays launch) | Critical (kills project)
- **Early warning**: What you'd notice in the first few hours that signals this risk is materializing

---

## Risk 1: GCP Billing / Quota Trap

- **Probability**: Medium
- **Severity**: High
- **What happened**: Personal GCP account hit the free-tier quota on Firebase Auth, or billing wasn't actually enabled (confusingly, Firebase project can "exist" without billing and then fail silently on Secret Manager). Spent 4 hours debugging what looked like IAM errors before realizing billing was the issue.
- **Mitigation**:
  - Verify billing active via `gcloud billing projects describe <PROJECT_ID>` before writing a single line of code
  - Set up budget alert at $10/month
  - Document the exact "click trail" in `docs/onboarding/gcp-setup.md`
- **Early warning**: Any API call returns `403 PERMISSION_DENIED` or `billing not enabled` in error message. **STOP. Check billing first.**
- **Fallback**: Switch to Firebase emulator for as much as possible; provision a new GCP project with fresh free-tier credits.

---

## Risk 2: IAM Permission Errors (Service Account Hell)

- **Probability**: High
- **Severity**: High
- **What happened**: Cloud Run SA could create itself but couldn't access Secret Manager. Or Firestore rules blocked all writes because `request.auth.token.company_id` custom claim was never set on test users. Cycled through `gcloud` commands for 6 hours.
- **Mitigation**:
  - Version-control IAM config as a shell script (`scripts/gcp_bootstrap.sh`) so mistakes are fixable by re-running
  - Use `gcloud iam service-accounts add-iam-policy-binding` with explicit role grants (never console clicks)
  - Write a tiny `verify_iam.py` that asserts the SA has all expected roles at boot
  - Set custom claims via Firebase Admin SDK in a seeding script, not by hand
- **Early warning**: First Secret Manager call returns `403`. First Firestore emulator write succeeds but production-mode write fails.
- **Fallback**: Use Application Default Credentials locally; defer real SA provisioning to Sprint 5 (deployment).

---

## Risk 3: Pre-commit Hook Infinite Fight

- **Probability**: Medium
- **Severity**: Medium
- **What happened**: `ruff` and `black` disagreed on formatting (you forgot `ruff` replaces `black` now), or `mypy` rejected every Pydantic v2 import. Each commit triggered 6 auto-fixes that then failed again on the next run.
- **Mitigation**:
  - Use `ruff` as the SINGLE formatter + linter (per 2026 best practice) — do NOT also install `black`, `isort`, `flake8`, `pyupgrade`
  - Pin all tool versions in `.pre-commit-config.yaml` to exact hashes, not `main` branches
  - Run `pre-commit run --all-files` on empty repo FIRST to confirm clean baseline
  - Use `mypy --install-types --non-interactive` and configure `pyproject.toml [tool.mypy]` to ignore missing imports for third-party libs initially
- **Early warning**: Any commit triggers more than 2 auto-fix cycles.
- **Fallback**: Start with only `ruff` + `detect-secrets`. Add `mypy` and `bandit` in Sprint 1 once the baseline compiles.

---

## Risk 4: ADK Setup Friction (New SDK, Undocumented Bugs)

- **Probability**: Medium
- **Severity**: Medium
- **What happened**: `google-adk` package failed to install on Python 3.11 due to a protobuf version pin. Or `adk web` launched but couldn't authenticate to Gemini because it expected `GOOGLE_API_KEY` but docs said `GEMINI_API_KEY`. Or the hello-world sample in the docs is out of date and references a removed method.
- **Mitigation**:
  - Start from the canonical [`adk-samples`](https://github.com/google/adk-samples) hello-world, copy-paste verbatim, don't customize
  - Document exact ADK version in `pyproject.toml` (pin to `==`, not `>=`)
  - Document exact env var name in `.env.template` based on what ADK actually reads
  - Have a fallback Gemini-only test (direct `google-generativeai` call) to prove the key works outside ADK
- **Early warning**: `adk web` hangs on startup, or returns an auth error unrelated to your key.
- **Fallback**: Open GitHub issue, ping ADK community Discord, temporarily bypass ADK and prove Gemini works standalone.

---

## Risk 5: Firestore Emulator Setup Problems

- **Probability**: Medium
- **Severity**: Medium
- **What happened**: Firebase CLI required a specific Node version you didn't have. Or the emulator worked but your Python client SDK couldn't connect because `FIRESTORE_EMULATOR_HOST` wasn't set before `firestore.Client()` was instantiated. Or Java was missing (emulator needs JRE).
- **Mitigation**:
  - Document exact Node version (18 LTS or 20 LTS) in README prerequisites
  - Install JRE as prerequisite
  - Set `FIRESTORE_EMULATOR_HOST` in a `conftest.py` session-scoped fixture, BEFORE any imports of the Firestore client
  - Provide a `make emulator` target that launches cleanly
- **Early warning**: `firebase emulators:start` prints Java-related error, or Python client connects to real Firestore instead of emulator (watch for latency differences).
- **Fallback**: Use `mockfirestore` Python library as a pure-Python fake; skip emulator-backed tests initially.

---

## Risk 6: Python Version Conflicts

- **Probability**: Low
- **Severity**: High
- **What happened**: Local Python was 3.12, pyproject requires **3.13** (Resolved Decision #1), but `uv` silently used system 3.12 because the virtual env wasn't activated. Tests passed locally because imports happened to work. CI on GitHub used 3.13 and everything broke.
- **Mitigation**:
  - Pin `requires-python = ">=3.13,<3.14"` in `pyproject.toml`
  - Use `uv python install 3.13` then `uv sync` (uv manages its own Python)
  - `.python-version` file contains `3.13` so pyenv/rye/uv all agree
  - CI matrix tests 3.13 only (no wide matrix for hackathon)
- **Early warning**: First `uv sync` shows a Python version mismatch warning.
- **Fallback**: `uv python install 3.13 --force-reinstall`; fall back to 3.12 only as last resort (verify ADK compatibility first).

---

## Risk 7: Dependency Resolution Hell

- **Probability**: Medium
- **Severity**: Medium
- **What happened**: `google-adk` pinned `google-generativeai==0.4.0`, `fastapi-cloudauth` required `cryptography<42`, `bandit` wanted `cryptography>=42`. No valid solution. Spent a day on pip backtracking.
- **Mitigation**:
  - Use `uv` (10–100x faster resolver, better error messages than pip)
  - Add deps incrementally: start with ADK + FastAPI only, verify lock, then add auth, then security tools
  - Keep `dev` and `security` dependency groups separate so a security tool conflict doesn't block app startup
- **Early warning**: `uv lock` takes more than 30 seconds or prints "backtracking" / "resolution impossible".
- **Fallback**: Drop the conflicting dev tool (e.g., skip `bandit` in Sprint 0, use `pip-audit` only).

---

## Risk 8: Documentation Overhead Eats the Whole Sprint

- **Probability**: Medium
- **Severity**: Medium
- **What happened**: Writing 7 ADRs + threat model + OWASP checklist + templates took longer than the infrastructure itself. By Apr 12, the docs were done but the CI pipeline wasn't working. User reviewer noted "lots of markdown, no green build."
- **Mitigation**:
  - Time-box each ADR to 30 min (you have the rationale already in [[Supply-Chain-Architecture-Decision-Analysis]])
  - Use templates aggressively — don't write from scratch
  - Sequence: infra first (Day 1), docs second (Day 2), polish (Day 3)
  - Treat ADR content as "consolidate existing research", not "new analysis"
- **Early warning**: End of Day 1 and CI pipeline is still red.
- **Fallback**: Ship minimal ADRs (1 page each), promote threat model to "draft" status, accept technical-debt note.

---

## Risk 9: ~~fastapi-cloudauth Library Abandonment~~ — RESOLVED

- **Status**: **Resolved.** Per Resolved Decision #4, we now use the
  first-party **`firebase-admin`** SDK with the `verify_id_token()`
  pattern — Google's official, actively maintained Python SDK.
- **Why this risk went away**: `firebase-admin` is backed by Google,
  has a large active community, and is the canonical way to verify
  Firebase ID tokens in server code. JWKS rotation is handled
  automatically by the SDK.
- **Residual risk**: Very low — if firebase-admin breaks, it breaks
  the entire Firebase Python ecosystem and Google will patch urgently.
- **New watch item**: Pin `firebase-admin>=6.5.0` and monitor for
  breaking changes in minor versions.

---

## Risk 11: Middleware Ordering Regression (Starlette LIFO Trap)

- **Probability**: Medium
- **Severity**: Medium
- **What happened**: A developer "cleaned up" the `create_app()`
  middleware stack in `main.py` and unknowingly reversed the order of
  `add_middleware` calls, not realizing Starlette applies them in LIFO
  order (last added = outermost). `FirebaseAuthMiddleware` became the
  outermost wrapper, which meant every 401/403 short-circuit response
  bypassed `AuditLogMiddleware` entirely. For weeks, production auth
  failures had no `correlation_id`, no `user_id`, no audit trail — and
  nobody noticed because the happy-path logs still worked.
- **Mitigation**:
  - Canonical order documented inline in `main.py` with a comment
    block explaining "last `add_middleware` call = outermost on the
    request" and listing the intended outer→inner order
  - Regression test (test-plan.md Area 4, Test 4.2) asserts
    `correlation_id` is present in the captured audit log for a
    request that returns 401 from the auth middleware
  - Code review checklist item: "If you touched `create_app()`, did
    you run Test 4.2 locally?"
- **Early warning**: A security review or incident investigation finds
  a 401 log line without `correlation_id`, or Test 4.2 fails in CI
  after a `main.py` edit.
- **Fallback**: Revert the `create_app()` change; re-run Test 4.2;
  add ordering assertions in a pytest-level smoke test that inspects
  `app.user_middleware` after `create_app()` returns.

---

## Risk 10: Scope Creep into Sprint 1 Territory

- **Probability**: High
- **Severity**: Medium
- **What happened**: "While we're setting up schemas, let's just write the Classifier logic really quickly..." By Day 3, half the Classifier was implemented, none of it tested, and the Sprint 0 gate criteria were still unmet.
- **Mitigation**:
  - Strict scope enforcement: Sprint 0 produces ZERO agent logic. hello_world_agent is the ONLY agent code.
  - Write agent logic in Sprint 1 when the PRD explicitly allows it
  - Treat temptation to "just add one thing" as a warning sign
- **Early warning**: You open `classifier.py` during Sprint 0 for any reason other than creating an empty file.
- **Fallback**: Aggressive scope cut — move all over-scope work to Sprint 1, fix gate criteria first.

---

## Risk 12: Supermemory Container-Tag Multi-Tenant Contract Drift

- **Probability**: Medium
- **Severity**: High (cross-tenant data leak would be a critical incident if it reached real users)
- **What happened**: Supermemory scopes memory via "container tags" rather than a first-class tenant primitive (see `docs/research/zettel-supermemory-python-sdk.md`). A single forgotten `container_tags=[company_id]` argument on a `memories.search(...)` call returned Company A's exception history to Company B's Impact Agent prompt. Leak discovered weeks after deploy because the data *looked plausible* — exceptions from a similar-sized 3PL — and nobody caught the cross-tenant ID in manual review.
- **Mitigation**:
  - `MemoryProvider` interface (ADR-002) accepts `company_id` as a **required positional arg** on every public method. Forgetting it is a type error, not a silent default.
  - `SupermemoryAdapter` (the concrete impl) internally constructs `container_tags=[company_id]` — application code never passes raw container tags.
  - `FakeSupermemoryClient` has the same interface and asserts `company_id` was passed on every call (test coverage for the contract itself).
  - Integration test: multi-tenant regression — write memory for `company_A`, search with `company_B`, assert empty result. Lives in `tests/integration/` once real Supermemory integration lands (Sprint 4).
  - Adapter boundary lowercases-and-strips `company_id` before tagging. Prevents `"COMPANY_abc"` vs `"company_abc"` silently creating split buckets.
- **Early warning**: Any code review where a Supermemory call uses positional args that look like "container_tags might be missing" OR any PR touching `memory/` that doesn't have a matching test update.
- **Fallback**: If a leak is observed in production, purge all memory for affected tenants via `memories.delete(container_tags=[compromised_ids])` (verify API support first — flagged open in zettel-supermemory-python-sdk.md "Further research"), then patch the adapter.

---

## Risk 13: Cloud Run SSE Response Buffering (Sprint 4 Streaming)

- **Probability**: Medium
- **Severity**: High (silent downgrade from streaming to batch — demo looks broken)
- **Sprint impact**: Materializes in Sprint 4 when `/triage/stream` is built. Logged here in Sprint 0 for cross-sprint awareness and because the `main.py` middleware stack and CORS config (Sprint 0) must not introduce response-body-buffering middleware that blocks SSE later.
- **What happened**: `/triage/stream` worked locally against uvicorn. Deployed to Cloud Run behind API Gateway. Browser `EventSource` connected, saw nothing for 30 seconds, then received the entire stream at once when the response closed. Judges thought the demo hung. Debug took a day — the issue was API Gateway buffering, not our code.
- **Mitigation**:
  - Sprint 4 streaming endpoint MUST set the three headers: `Cache-Control: no-cache`, `X-Accel-Buffering: no`, `Connection: keep-alive` (see `docs/research/zettel-fastapi-sse-cloud-run.md`).
  - Sprint 4 MUST emit a keep-alive comment `: ping\n\n` every 15s during agent thinking gaps.
  - Sprint 5 deploy path MUST be **Cloud Run direct**, NOT Cloud Run behind API Gateway. Documented in `docs/research/Supply-Chain-Deployment-Options-Research.md` evaluation.
  - Sprint 4 acceptance test: `curl -N https://.../triage/stream` held open for 30+ seconds observes events arriving progressively (wall-clock timestamps per event), AND a browser `EventSource` does the same.
  - Sprint 0 middleware: ensure no middleware in the canonical stack (AuditLog, FirebaseAuth, InputSanitization, CORS) buffers response bodies. Audit at Phase C4 review.
- **Early warning**: During Sprint 4, if curl output all arrives at once at connection close, OR if `EventSource.onmessage` fires only after disconnect, STOP and check headers + infra path.
- **Fallback**: Non-streaming `/triage` endpoint that returns the full `TriageResult` as JSON (ADR-004 names this as an explicit fallback). The same event generator feeds either endpoint — wrap in a list-accumulator for the sync version. Ship the sync endpoint for the demo if streaming isn't green by Sprint 4 Day 1.

---

## Mitigation Summary

| # | Risk | Mitigation Cost | Implemented? |
|---|------|-----------------|--------------|
| 1 | GCP billing | 10 min | Pre-sprint check |
| 2 | IAM hell | 1 hr scripting | Day 1 |
| 3 | Pre-commit fights | 30 min | Day 1 |
| 4 | ADK friction | 30 min (copy sample) | Day 2 |
| 5 | Emulator setup | 30 min | Day 2 |
| 6 | Python versions | 15 min | Day 1 |
| 7 | Dep resolution | Use `uv` | Day 1 |
| 8 | Doc overhead | Time-box | Day 2–3 |
| 9 | Library abandonment | 15 min due diligence | Day 1 |
| 10 | Scope creep | Discipline | Every day |
| 11 | Middleware ordering regression | 10 min (regression test 4.2) | Day 2 |
| 12 | Supermemory container-tag contract | 15 min (required-positional signature + Fake client assertions) | Day 1 (interface shape) + Sprint 4 integration regression |
| 13 | Cloud Run SSE buffering | Documented; enforced in Sprint 4 + Sprint 5 deploy path | Sprint 4 + 5 |

**Most likely failure mode**: Risks 2, 8, and 10 combined — IAM eats Day 1, docs eat Day 2, scope creep eats Day 3, sprint ends red.

**Watch metric**: End of each day, check sprint gate criteria (§17 of PRD v2). Any still-red item after its planned day = raise flag immediately.

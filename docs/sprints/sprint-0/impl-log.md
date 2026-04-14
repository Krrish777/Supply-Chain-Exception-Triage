---
title: "Sprint 0 Impl Log"
type: deep-dive
domains: [supply-chain, sdlc]
last_updated: 2026-04-14
status: active
---

# Sprint 0 Implementation Log

> Dev diary — what got built in what order, what surprised us, decisions made mid-sprint.

## Scope summary

Sprint 0 shipped the foundation: tooling + rules + 32-test plan + 6 Pydantic schemas + 5 middleware files + memory stub + hello_world ADK agent + FastAPI bootstrap + Firestore emulator config + 9 documentation files + the canonical logger + 8 ADRs.

**Lines produced:** ~4,500 (src + tests combined, excluding docs).
**Tests passing:** 57 (1 integration-skipped without GEMINI_API_KEY).
**Coverage on pure-logic paths:** 92%.

## Day-by-day

### Phase A — Plan (~3h)

- Read existing Sprint 0 PRD v1. Cross-referenced against the 6 just-authored `.claude/rules/*` files + CLAUDE.md.
- Found 10 reconciliation deltas (flat vs modular layout, Supermemory stays vs defers, CompanyProfile.to_markdown missing, set_custom_claims missing, A2A has no ADR, coverage gate softened, UserContext split, timeline slip, evalsets-not-on-Coordinators, Zettelkasten format).
- Archived PRD v1 → `prd-v1-archived.md`. Authored PRD v2 with "Changes from v1" section as a hardened diff.
- Copied 5 vault notes into `docs/research/` (Sprint-Plan-Spiral-SDLC, Agent-Spec-Coordinator, Agent-Spec-Classifier, Agent-Spec-Impact, Firestore-Schema-Tier1).
- Wrote ADA digest (~2 pages).
- Wrote 5 Obsidian Zettels from web research: Supermemory SDK, ADK `before_model_callback`, FastAPI SSE + Cloud Run, Firestore multi-tenant, vault Coordinator inconsistency.
- Rewrote `test-plan.md` with 32 tests (12 schema + 1.10b + 1.12b + 13 middleware + 3 sanitize + 2 audit + 1 ADK + 1 emulator + 2 CORS + 2 pre-commit + 2 secret/claims). Later net-new tests pushed this to 57.

### Phase B — Risk (~30m)

- Authored ADR-008 (A2A protocol — always scaffold, never hand-write).
- Amended ADR-005 with the Tier-1-advisory-coverage caveat.
- Appended Risk 12 (Supermemory container-tag multi-tenant contract) and Risk 13 (Cloud Run SSE buffering) to `risks.md`.

### Phase C prep (~30m) — unplanned bug hunt

- Extended `.claude/rules/placement.md` + `check_placement.py` allowlist for `scripts/`, `infra/`, `firebase.json`, `tests/fixtures/`, `.secrets.baseline`, `CONTRIBUTING.md`, `SECURITY.md`.
- **Found 2 pre-existing bugs in `check_placement.py`**:
  1. `fnmatch` doesn't treat `**` recursively — every file directly in `core/`, `middleware/`, `runners/`, `utils/` was silently being rejected by the hook. Switched to `PurePosixPath.full_match()` (Python 3.13+).
  2. `.lstrip("./")` mangled dotfiles — `.env` → `env`, `.secrets.baseline` → `secrets.baseline`. Switched to `.removeprefix("./")`.
- Verified with a 27-case allow/reject matrix.
- Found `[tool.pytest.ini]` typo in `pyproject.toml` (should be `ini_options`) — was silently ignoring `asyncio_mode=auto` + markers + addopts. Fixed.

### Phase C — Engineer (~8h, strict TDD)

Each sub-phase ends with RED → implementation → GREEN.

- **C1 — Scripts:** `setup.sh` + `gcp_bootstrap.sh` + `seed_firestore.py` + `deploy.sh` + **`set_custom_claims.py`** (net-new from web research — Firebase custom claims require Admin SDK server-side). 6 seed-JSON skeletons in `scripts/seed/`.
- **C2 — Core config:** `core/config.py` with `Settings`, `get_settings()`, `get_secret()` (env fallback → GCP Secret Manager), `get_firestore_client()`, `SecretNotFoundError`. 5 tests. **Added `core/config.py` to ruff TID251 per-file-ignores** — this is the DI chokepoint where framework-specific imports are allowed.
- **C3 — Schemas:** 6 Pydantic v2 models + `render_learned_preferences()` helper. 14 schema tests including two net-new (Test 1.10b + 1.12b). `UP042` caught `class X(str, Enum)` → migrated to `StrEnum`. Vault research confirmed the Coordinator spec's internal inconsistency (lines 62–114 vs 191–213) about UserContext markdown; resolved by splitting into `UserContext.to_markdown()` (3 sections) + `CompanyProfile.to_markdown()` (Business Context) + `render_learned_preferences()` helper.
- **C4 — Middleware:** 5 files (`firebase_auth`, `cors`, `audit_log`, `input_sanitization`, `rate_limit`-stub) + 13 tests + 2 net-new (Risk 11 stack-ordering test at `tests/unit/runners/test_main.py` is stronger than log-capture-only Test 4.2).
- **C5 — Memory stub:** `MemoryProvider` ABC + `SupermemoryAdapter` skeleton. Risk 12 mitigation: every method takes `company_id` as required positional arg; `FakeSupermemoryClient` asserts `company_id` on every call.
- **C6 — hello_world agent:** `LlmAgent(model="gemini-2.5-flash")` + co-located prompt + `agent_runner.py` framework-portability shim + 3 unit tests + integration test (skipped without GEMINI_API_KEY) + `evals/hello_world/greeting.evalset.json`.
- **C7 — FastAPI bootstrap:** `main.py::create_app()` with canonical middleware LIFO order. 2 tests including a stack-ordering assertion as the stronger Risk 11 regression guard.
- **C8 — Firestore emulator:** `infra/firestore.rules` (multi-tenant), `infra/firestore.indexes.json` (9 composite indexes), `firebase.json`, session-scoped emulator fixture in `tests/conftest.py`, 1 integration test (auto-skips if emulator not running).
- **C9 — Fakes:** `fake_gemini.py`, `fake_firestore.py` (mockfirestore), `fake_supermemory.py` (MemoryProvider-conforming, asserts company_id).
- **C10 — Docs:** README untouched (user's), `CONTRIBUTING.md`, `SECURITY.md`, `docs/security/threat-model.md`, `docs/security/owasp-checklist.md`, 5 templates in `docs/templates/`.

### Phase C remediation (CR1-9, ~1h)

Code-reviewer surfaced 15 ruff errors + 7 substantive issues. Fixed:

- **CR1 — TID251 blocker** (§17 #14 sprint gate): added `"scripts/**" = ["TID251", "T201", "T203"]` per-file-ignore + extended `.claude/rules/imports.md` to allow `firebase_admin` / `google.cloud.firestore` in `scripts/` (admin-only CLIs).
- **CR2 — Ruff cleanup:** PLR0911 factored via `_reject(code, error)` helper in firebase_auth; dead `noqa: BLE001` removed; empty `TYPE_CHECKING` blocks dropped; raw-string docstrings fixed; `scripts/*.py` main() docstrings added; `open()` → `Path.open()`; ERA001/RUF002 added to tests per-file-ignores.
- **CR3 — Schema bug:** `ShipmentImpact.deadline: str → datetime` (tz-aware per `models.md` §2).
- **CR5 — rate_limit smoke test:** 1-line parity test (`test_rate_limit_is_pass_through`).
- **CR6 — Narrow exception:** `except (ValueError, firebase_auth.CertificateFetchError)` in firebase_auth — catches the legit cases (firebase-admin #766 + JWKS transients) without swallowing bugs.
- **CR8 — Tighter typing:** `learned_priorities: dict[str, Any] → dict[str, float]` (Impact agent reads numeric weights).
- **CR9 — `get_firestore_client()` behavior fix:** exports `settings.firestore_emulator_host` to the real env var before client construction (the SDK reads env at init time).
- Deleted leftover root-level `main.py` stub (uv init residue).
- Fixed `pyproject.toml` `[tool.pytest.ini]` → `ini_options` typo found during Phase C prep.

### Logger phase (L1-L5, L7-L9)

- **L1 — utils/logging.py:** structlog bridged to stdlib via `structlog.stdlib.ProcessorFormatter`. Handlers: Rich console + 4 rotating file handlers (app daily 30d, error 10MB×5, json daily 30d, api daily 30d) + JSON stdout fallback for Cloud Run. Processor chain: `merge_contextvars → _add_request_id (stdlib-compat) → _drop_pii → add_log_level → TimeStamper → wrap_for_formatter`. 5 domain helpers (`log_agent_invocation`, `log_tool_call`, `log_firestore_op`, `log_api_call`, `log_auth_event`).
- **L2 — Architecture-layers.md:** narrow exception for `utils/logging.py` to import `rich` + `structlog` + `logging.handlers`.
- **L3 — `.claude/rules/logging.md`:** mandates `get_logger` usage, bans `print()` / raw `logging.getLogger` / raw `structlog.get_logger`, documents log levels, domain helpers, PII rules, request_id propagation via `structlog.contextvars.bind_contextvars`, test pattern.
- **L4 — `pyproject.toml`:** added `rich>=13.9.0` dep, added `T20` ruff rule + scripts per-file-ignore.
- **L5 — `middleware/audit_log.py` retrofit:** now uses `get_logger` from `utils.logging`. `AuditLogMiddleware.dispatch` calls `structlog.contextvars.clear_contextvars()` + `bind_contextvars(correlation_id, request_id)` per request, with `request_id_var.set()` as stdlib-compat fallback for uvicorn access logs.
- **L7 — `.gitignore`:** `logs/` added.
- **L8 — `Settings`:** added `log_level`, `log_to_files`, `logs_dir` fields.
- **L9 — `log_output` pytest fixture:** session-swap structlog config for `structlog.testing.LogCapture()` per test, restore on teardown. `tests/unit/utils/test_logging.py` uses it.

**L6 (retrofit middleware with lifecycle events) deferred.** The logger module is callable from everywhere; adding `logger = get_logger(__name__)` + per-method `.info("event", ...)` calls across 8 files is boilerplate that should land incrementally as agents are built Sprint 1+.

## Surprises worth logging

1. **Pre-existing `check_placement.py` bugs (fnmatch `**` + dotfile lstrip)** — these were silently rejecting legit writes. Caught by a sanity-test matrix I added in Phase C prep. Without that matrix, they would have manifested as random "why can't I write this file?" errors through Phase C.
2. **`[tool.pytest.ini]` typo** — was silently ignoring `asyncio_mode=auto` + strict markers. Caught when `pytest --collect-only` warned "Unknown config option: ini". Had been failing quietly since project init.
3. **`BaseHTTPMiddleware` deprecation** — Starlette's official guidance is to migrate to pure ASGI before Starlette 1.0. All 5 middleware files use `BaseHTTPMiddleware`. Documented in vault Zettel `Supply-Chain-Zettel-BaseHTTPMiddleware-Risk`. Sprint 4 refactor before SSE.
4. **`firebase_admin.auth.verify_id_token` exception hierarchy** — `ExpiredIdTokenError` and `RevokedIdTokenError` both extend `InvalidIdTokenError`. `except` order matters. Our code has correct order (specific first).
5. **`check_revoked=True` is not the default** — revoked tokens are valid until expiry (up to 1 hour). Documented as a Sprint 4 hardening item in vault Zettel `Supply-Chain-Zettel-Firebase-Admin-Verify-Token`.
6. **Vault Coordinator spec had an internal inconsistency** — lines 62-114 describe UserContext's markdown as having 5 sections; lines 191-213 split them into 4 XML blocks. Resolved in our implementation and documented in `docs/research/zettel-vault-coordinator-inconsistency.md`.
7. **structlog contextvars has a subtle sync/async FastAPI gotcha** — raw `ContextVar` set in middleware sync setup may not propagate to async route handlers. Canonical fix is `structlog.contextvars.bind_contextvars`. Documented in vault Zettel `Supply-Chain-Zettel-Structlog-Async-Contextvars`. Logger retrofit uses the canonical pattern.

## Files authored / modified this sprint

60+ files created; 8 modified. See `git status` at tag `v0.1.0-sprint-0` for the full diff.

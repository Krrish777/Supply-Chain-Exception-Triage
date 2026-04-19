---
title: "Sprint 3 PRD — Tier 1 Closeout (Pipeline + API + UI + Deploy)"
type: prd
sprint: 3
window: "2026-04-19 to 2026-04-28"
deadline: "2026-04-28"
last_updated: 2026-04-18
status: approved-pending-user
supersedes: "./prd-v1-archived.md"
---

# Sprint 3 PRD — Tier 1 Closeout

> **Plan authored after** 2026-04-18 research session (40+ decisions captured in `docs/sessions/2026-04-18-research-session-decisions.md`) and 7 research docs in `docs/research/`.
> **Supersedes:** `prd-v1-archived.md` (the original LlmAgent-Coordinator + full Supermemory-injection spec). This PRD trims the scope to what ships for the Apr 28 deadline.
> **Sprint window:** Apr 19 → Apr 28 (10 days, single continuous build session).
> **Exit gate:** Pipeline + SSE API + auth + dashboard UI + Cloud Run URL all live.

---

## 1. Objective

Ship the Tier 1 prototype: a working end-to-end Supply Chain Exception Triage demo that a judge can visit, sign in with Google, paste (or pick) a scenario, and watch an ADK multi-agent pipeline classify + impact-assess an exception in real time — with the full run persisted to Firestore for a history view.

**One-sentence goal:** On Apr 28, a judge visits our Cloud Run URL, signs in with Google, clicks the NH-48 Ramesh Kumar scenario, and within ~8 seconds sees the Classifier + Impact pipeline stream progress + return a correct structured `TriageResult` (`severity="CRITICAL"`, priority shipment `SHP-2024-4821`), all recorded in Firestore's history list.

---

## 2. Scope (IN)

### 2.1 Pipeline orchestration

- `SequentialAgent("triage_pipeline", sub_agents=[classifier_agent, impact_agent])` wrapped in a new module `modules/triage/pipeline.py`.
- `before_agent_callback` on **Classifier** — Rule B (safety override) keyword short-circuit. Keyword list: 16 English + 10 Hindi-transliterated terms, NFKC + casefold normalization. On match: write placeholder classification to state, short-circuit pipeline, mark `triage:skip_impact=True`.
- `before_agent_callback` on **Impact** — reads `triage:classification` from state + `triage:skip_impact`. Rule B → skip, Rule C (regulatory_compliance) → force-run, Rule F (LOW severity non-regulatory) → skip with `impact=None`. Priority order: B > C > F.
- Per-tool span wiring via `before_tool_callback` / `after_tool_callback` on fetcher agents (for OTel + cost attribution).
- No Coordinator `LlmAgent`. No Supermemory / `UserContextProvider`. No dynamic context injection. (All Tier 2+.)

**Reference doc:** `docs/research/coordinator-orchestration-patterns.md` — full code skeletons in §15.

### 2.2 API layer

| Endpoint | Method | Purpose | Response |
|---|---|---|---|
| `/api/v1/triage` | POST | Run pipeline on `{event_id}` or `{raw_content}`, stream events via SSE | `text/event-stream` with `agent_started` / `tool_invoked` / `agent_completed` / `partial_result` / `complete` / `error` / `done` frames |
| `/api/v1/exceptions` | GET | Paginated tenant-scoped history | `Page[ExceptionPublic]` envelope |
| `/api/v1/auth/onboard` | POST | First-login custom-claim seeding for Google OAuth users | `{user_id, company_id, requires_token_refresh: true}` |
| `/api/v1/classify` / `/api/v1/impact` | (existing) | Debug-only; keep behind feature flag or restrict to dev | Unchanged |

**Reference docs:** `docs/research/fastapi-sse-api-design.md`, `docs/research/firebase-auth-oauth-multitenancy.md`.

### 2.3 Firestore

- Rewritten `infra/firestore.rules` covering all 12 collections (adds `routes`, `hubs`, `triage_results`, `audit_events`).
- Rewritten `infra/firestore.indexes.json` — 12 composite indexes.
- Consolidated `scripts/seed_all.py` — replaces 4 overlapping seeders. CLI: `--target=emulator|prod|demo --wipe --collections=csv`.
- Populate 3 stub seed files with full content: `companies.json` (SwiftLogix + NimbleFreight), `users.json` (2 per tenant, Priya + others), `festival_calendar.json` (Diwali / Holi / Eid windows).
- Fix `get_affected_shipments` tenant-leak: add `company_id` filter clause.
- Write `triage_results/{id}` and `audit_events/{id}` on every pipeline run.

**Reference doc:** `docs/research/firestore-utilization-audit-tier1.md` — full JSON + rules in §7 + §10.

### 2.4 Middleware + hardening

- Firebase Auth middleware already exists. Add: token-age cap (3600s), revocation check on privileged routes, `audit_event` emission on login / permission_denied / rate_limit_hit.
- slowapi per-IP rate limiting: 10 req/min on `/api/v1/triage`.
- CORS: allow only configured UI origin via `CORS_ALLOWED_ORIGINS`.
- `max_output_tokens`: 1024 on fetchers, 2048 on formatters.
- `tenacity` retry wrapper on Impact agent (1 retry, exp backoff with jitter).
- OTel spans + Cloud Trace exporter per-agent and per-tool. `gen_ai.usage.input_tokens` / `output_tokens` on every agent span.
- SIGTERM span flush handler.

### 2.5 Dashboard UI (framework TBD — PRD stays framework-agnostic)

Three screens:

1. **Landing + Sign-in** — hero + "Sign in with Google" + 2-line explainer.
2. **Triage console** — scenario picker (NH-48 / FSSAI / safety) + paste textarea + Run button + SSE event log panel + `TriageResult` card + before/after narrative section. Raw JSON behind a "details" toggle.
3. **History** — list view of past exceptions (`GET /api/v1/exceptions`). Click → (optional Tier 2) detail page. Tenant-scoped.

UI binds to:
- `POST /api/v1/auth/onboard` (first login flow after Firebase Auth + custom claim seeding).
- `POST /api/v1/triage` (via `fetch` + `ReadableStream` reading SSE frames; standard `EventSource` rejected because we send bearer tokens).
- `GET /api/v1/exceptions` (history page, cursor pagination).

### 2.6 Cloud Run deploy

- Dockerfile per `docs/research/gcp-proper-utilization.md` §9 (multi-stage uv + non-root + `tini` for SIGTERM→OTel flush).
- Project: fresh `sct-prod` (claims $300 new-user credits). Region `asia-south1`.
- Service account with Workload Identity; roles: `datastore.user`, `secretmanager.secretAccessor` (per-secret), `aiplatform.user` (if Vertex flipped — optional), `logging.logWriter`, `cloudtrace.agent`.
- Secrets via `--set-secrets` (Gemini API key, Firebase admin config).
- `min-instances=1` for 48h around demo; scale-to-zero otherwise.
- Firebase Hosting serves the UI, rewrites `/api/*` to Cloud Run.
- Budget alerts: $10 / $25 / $50 on `sct-prod`.
- Staging deploy Apr 26, smoke test 24h, flip prod Apr 27.

### 2.7 Tests + evalsets

- ~25 new pytest unit tests across: Rule B callback, Rule C/F callback, pipeline assembly, SSE event mapping, runner cancellation, `/auth/onboard` handler, slowapi integration.
- 1 integration test: `tests/integration/test_triage_pipeline.py` — seeds Firestore emulator + runs full NH-48 pipeline + asserts structured `TriageResult` matches spec.
- 1 SSE integration test: `tests/integration/test_triage_sse.py` — asserts event ordering + final frame.
- Classifier evalset: 15 cases (**6 happy + 4 edge + 3 safety + 2 adversarial**) in `evals/classifier/evalset.json`.
- Impact evalset: 10 cases (**5 happy + 2 skip-cases + 2 edge + 1 failure**) in `evals/impact/evalset.json`.
- **No Coordinator evalset** (ADK bug #3434 — sub-agent trajectory scoring unreliable on SequentialAgents).

---

## 3. Out-of-scope (deferred)

| Item | Deferred to |
|---|---|
| LlmAgent Coordinator with `sub_agents` + `transfer_to_agent` | Not planned — SequentialAgent+callbacks is the permanent pattern |
| Rules A (WhatsApp voice urgency), D (festival/monsoon context), E (D2C reputation tag) | Tier 2 (require Supermemory) |
| Supermemory / `UserContextProvider` / dynamic context injection | Tier 2 |
| `AgentRunner` framework-portability abstraction | Post-Apr-28 |
| Resolution agent (Generator-Judge) | Tier 2 |
| Communication agent, Route Optimizer | Tier 2/3 |
| React dashboard with Maps | Tier 3 |
| Exception detail page | Tier 2 (Tier 1 has list only) |
| Multi-turn Coordinator conversations | Tier 2 |
| Tamil / Telugu / Kannada support | Tier 2 |
| Vertex AI migration | Optional pre-Apr-28 (2-hour follow-up) or Tier 2 |
| BigQuery analytics / log sink | Tier 2 |
| Agent Engine / GKE | Not planned |
| Gemini 2.5 context caching | Tier 2 |

---

## 4. Acceptance criteria (Sprint 3 exit gate)

All must be ✅ before Apr 28 submission.

| # | Criterion | Verification |
|---|---|---|
| 1 | All pytest unit tests pass | `uv run pytest tests/unit/` → 0 failures |
| 2 | Full pipeline integration test passes (NH-48) | `uv run pytest tests/integration/test_triage_pipeline.py -v` |
| 3 | SSE integration test passes (event order + final frame) | `uv run pytest tests/integration/test_triage_sse.py -v` |
| 4 | `ruff check .` clean | CI pass |
| 5 | `uv run mypy src` clean | CI pass |
| 6 | `uv run lint-imports` clean | CI pass |
| 7 | Classifier evalset ≥13/15 pass at configured thresholds | `adk eval modules/triage/agents/classifier evals/classifier/evalset.json` |
| 8 | Impact evalset ≥8/10 pass | `adk eval modules/triage/agents/impact evals/impact/evalset.json` |
| 9 | NH-48 end-to-end live via `adk web` against seeded emulator | Manual smoke documented in `impl-log.md` |
| 10 | Cloud Run URL responds 200 on `/healthz`, completes full triage pipeline on `/api/v1/triage` with judge credentials | Manual verification from staging + prod |
| 11 | Dashboard UI runs all 3 flagship scenarios end-to-end from Firebase Hosting URL | Apr 27 full dress rehearsal |
| 12 | OTel spans visible in Cloud Trace with per-agent + per-tool waterfall | Screenshot in `impl-log.md` |
| 13 | Budget alerts configured at $10 / $25 / $50 on `sct-prod` | `gcloud billing budgets list` |
| 14 | Firestore rules cover all 12 collections; catch-all deny confirmed | Manual rule-test via emulator |
| 15 | `audit_events` collection populated per run with correlation_id + user_id + company_id | Spot-check in Firestore console post-rehearsal |

### Cut-line (if we slip)

Defer in this order: **Impact evalset → History page → evalset pass thresholds (demote to advisory)**. Triage console + pipeline + auth + Cloud Run must all ship.

---

## 5. Day-by-day build sequence

| Day | Date | Deliverables |
|---|---|---|
| 1 | Apr 19 | **Hygiene**: commit uncommitted `core/llm.py` work + tests + config + deps + `.env.template` in its own commit; fix pre-existing `test_classification.py` failure in a second commit; seed emulator; live-test Impact in `adk web` with NH-48 scenario; document screenshot + any fixes in `impl-log.md` |
| 2 | Apr 20 | **Callbacks**: implement `modules/triage/pipeline/callbacks.py` with `_rule_b_safety_check`, `_rule_cf_skip_check`. Safety keyword list (EN + HI). Unit tests for each. Commit. |
| 3 | Apr 21 | **Pipeline + runner**: `modules/triage/pipeline.py` (SequentialAgent factory), `runners/triage_runner.py` blocking path. Integration test `tests/integration/test_triage_pipeline.py`. Commit. |
| 4 | Apr 22 | **SSE**: `runners/triage_runner.py` streaming path (`_triage_event_stream`), `POST /api/v1/triage` endpoint. SSE integration test. Commit. |
| 5 | Apr 23 | **API + auth hardening**: `POST /api/v1/auth/onboard`, `GET /api/v1/exceptions`, slowapi rate limit, OTel wiring, `audit_event` emissions, tenacity retry on Impact. Commit per feature. |
| 6 | Apr 24 | **Firestore fixes**: rewrite `firestore.rules` + `firestore.indexes.json`; build `scripts/seed_all.py`; populate 3 stub seed files; fix `get_affected_shipments` tenant-leak; write `triage_results` + `audit_events` on run. Commit per concern. |
| 7 | Apr 25 | **Evalsets**: capture-then-edit Classifier 15 cases + Impact 10 cases. Run `adk eval`, iterate prompts/tools minimally until thresholds pass. Commit. **Start UI** (framework decision lands before this day). |
| 8 | Apr 26 | **UI + staging deploy**: finish Landing / Triage console / History. `gcloud run deploy` to `sct-staging`. Smoke test. Debug Cloud Run-specific issues (buffering, SSE timeouts). Commit. |
| 9 | Apr 27 | **Prod deploy + full dress rehearsal**: `gcloud run deploy` to `sct-prod`. `min-instances=1`. Full rehearsal with all 3 scenarios. Fix any last-mile issues. Cut release commit. |
| 10 | Apr 28 | **Pre-submit smoke + submission**: morning smoke test end-to-end. Submit. Update `impl-log.md` + `test-report.md`. |

Cut-line activations trigger day-level replanning documented in `impl-log.md` the day they happen.

---

## 6. Dependencies + references

- **Decisions:** `docs/sessions/2026-04-18-research-session-decisions.md` (40+ Q&A decisions, single source of truth).
- **Research docs (read in this order on Day 1):**
  1. `docs/research/coordinator-orchestration-patterns.md`
  2. `docs/research/firestore-utilization-audit-tier1.md`
  3. `docs/research/fastapi-sse-api-design.md`
  4. `docs/research/firebase-auth-oauth-multitenancy.md`
  5. `docs/research/llm-quotas-rate-limits.md`
  6. `docs/research/observability-otel-cloud-trace.md`
  7. `docs/research/gcp-proper-utilization.md`
- **ADR:** `docs/decisions/adr-009-coordinator-pattern.md` (documents SequentialAgent+callbacks choice).
- **Existing rule files** (load on touching matching paths): `.claude/rules/{agents,api-routes,firestore,imports,architecture-layers,placement,testing,deployment,observability}.md`.

---

## 7. Risks

See `risks.md` for the full pre-mortem. Top 5:

1. **Gemini quota 429 during demo** → Mitigation: Tier 1 paid quota, `min-instances=1`, budget alerts, `tenacity` retry, emergency kill-switch documented.
2. **SSE breaks on Cloud Run (buffering / timeout)** → Mitigation: `X-Accel-Buffering: no` header, HTTP/2, Cloud Run timeout bumped to 3600s, Day 8 dedicated to Cloud-Run-specific debugging.
3. **Evalset doesn't hit thresholds** → Mitigation: rubric-based scoring (not exact-match), 13/15 + 8/10 bar (85% and 80%), prompt iteration budget on Day 7, ultimately demote to advisory per cut-line.
4. **Custom-claim refresh bug (user signs in but claims not active)** → Mitigation: explicit `user.getIdToken(true)` call post-onboard documented in frontend research; integration test covers the round-trip.
5. **Tenant-leak via `get_affected_shipments`** → Mitigation: Day 6 explicit fix with regression test.

---

## 8. Definition of Done per deliverable

| Deliverable | Done when… |
|---|---|
| Callback | Unit test + integration test + `audit_event` on entry + one-line docstring |
| Pipeline factory | Creates SequentialAgent, wired to 2 sub-agents, callbacks registered, returns root_agent compatible with `adk web` |
| SSE runner | Streams all 7 event types in correct order, handles cancel, emits final `done`, returns proper `text/event-stream` headers |
| API route | Envelope matches `.claude/rules/api-routes.md` §7, status codes per §8, auth + tenant check + 1 happy + 1 error pytest |
| Firestore rule change | Emulator test proves rule denies cross-tenant + allows same-tenant |
| Seed file | Idempotent write via `seed_all.py`, referenced by at least one existing agent tool or test |
| Evalset | JSON conforms to ADK schema, at least 80% pass via `adk eval` at configured thresholds |
| UI screen | Auth-gated (except Landing), API-wired, renders SSE stream or list, matches endpoint contracts |
| Cloud Run deploy | Service responds 200 on `/healthz`, 200 on authed `/api/v1/exceptions`, SSE stream completes end-to-end |

---

## 9. Open items (resolve Day 1 of build session)

1. **UI framework choice** — user deferred in research session; tell me at Day 1 so UI plan is concrete. Research doc stays framework-agnostic regardless.
2. **Vertex AI vs direct Gemini API** — user deferred. Default Tier 1 = direct API. Vertex migration is a 2-hour optional follow-up.
3. **Firestore region** — default `asia-south1`. Confirm at Day 6.
4. **Gemini API Tier 1 paid upgrade** — confirm billing enabled on `sct-prod` by Day 5; free-tier RPM insufficient for rehearsal.

---

## 10. Success metrics

- Apr 28 demo: judge runs all 3 scenarios, sees <10s end-to-end for each, can browse history, sign out cleanly.
- All 15 acceptance criteria green in `test-report.md`.
- Cloud Run cost for 48h demo window < $10.
- Gemini cost for demo window < $3.
- Zero Gemini 429s during full dress rehearsal.
- Zero uncaught exceptions in Cloud Run logs during rehearsal.

---

## 11. Post-Sprint-3 (Tier 2 preview)

1. Resolution agent (Generator-Judge) — highest-value follow-on.
2. Supermemory + `UserContextProvider` — unlocks Rules A/D/E + learned overrides.
3. Coverage gate flip to `--cov-fail-under=90` on pure-logic paths.
4. Vertex AI migration if not done pre-Apr-28.
5. Full BigQuery log sink + Cloud Monitoring custom dashboards.
6. Exception detail page.
7. Cross-tenant analytics view for ops staff.

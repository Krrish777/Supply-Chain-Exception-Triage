---
title: "Sprint 3 Implementation Log"
type: impl-log
sprint: 3
last_updated: 2026-04-18
status: scaffold-to-be-filled-during-build
---

# Sprint 3 Implementation Log

Dev diary — one entry per day during the build session. Fill as we go.

---

## Day 1 — 2026-04-19 (planned)

**Planned deliverables:**
- Commit uncommitted `core/llm.py` + tests + config + deps + `.env.template` (atomic commit 1)
- Fix pre-existing `test_classification.py` failure: dict vs `list[KeyFact]` (atomic commit 2)
- Seed emulator via current `scripts/seed_emulator.py` + `seed_impact_demo.py`
- Live-test Impact in `adk web` with NH-48 scenario; document output screenshot
- Resolve UI framework decision (user ask)

**Actuals:** (to be filled)

**Blockers / deviations:** (to be filled)

---

## Day 2 — 2026-04-20 (planned)

**Planned:**
- `modules/triage/pipeline/_constants.py` (safety keywords)
- `modules/triage/pipeline/callbacks.py` (`_rule_b_safety_check`, `_rule_cf_skip_check`)
- `tests/unit/triage/test_pipeline_callbacks.py` (U-1 … U-10)
- Atomic commit

**Actuals:** (to be filled)

---

## Day 3 — 2026-04-21 (planned)

**Planned:**
- `modules/triage/pipeline.py` factory
- `runners/triage_runner.py` blocking path
- `tests/unit/triage/test_pipeline_factory.py` (U-11 … U-13)
- `tests/unit/runners/test_triage_runner.py` (U-14 … U-18 blocking-only subset)
- `tests/integration/test_triage_pipeline.py` (I-1 NH-48)
- Atomic commits

**Actuals:** (to be filled)

---

## Day 4 — 2026-04-20 (actual — pulled in two days from plan)

**Planned:**
- `runners/triage_runner.py` streaming path (`_triage_event_stream`)
- `runners/routes/triage.py` (`POST /api/v1/triage`)
- `tests/integration/test_triage_sse.py` (I-8 … I-11)
- Atomic commit

**Actuals:**
- `runners/triage_runner.py` extended with `_triage_event_stream(event_id, raw_text)
  -> AsyncIterator[dict[str, Any]]`, shared `_assemble_triage_result` + parse helpers
  with the Day 3 blocking path. Frame contract (7 types per PRD §2.2): `agent_started` /
  `tool_invoked` / `agent_completed` / `partial_result` / `complete` / `error` / `done`.
  Translation helper `_frames_for_event` converts ADK Event shape into our stable contract
  (don't leak ADK internals per `.claude/rules/agents.md` §10).
- `runners/routes/triage.py` (NEW) with `APIRouter(prefix="/api/v1/triage")` and
  `POST /` returning `StreamingResponse(media_type="text/event-stream")` with
  `X-Accel-Buffering: no` (Cloud Run footgun). Auth via `Depends(get_current_user)`
  reading `request.state` set by `FirebaseAuthMiddleware` — gives dep-override seam for tests.
- `modules/triage/models/api_envelopes.py` gained `TriagePayload(event_id | raw_text)`
  with `model_validator(mode="after")` requiring at least one non-whitespace field
  (+ `extra="forbid"` per `.claude/rules/models.md` §9).
- `main.py` now `app.include_router(triage_router)` after the middleware stack.
- `tests/integration/test_triage_sse.py` (NEW): I-11 (4 variants: empty, both empty,
  whitespace, extra field), I-9 (Rule B short-circuit via `raw_text`, no Gemini),
  I-10 (client disconnect mid-stream), I-8 (happy path; Gemini-gated, skipped without key).
- Verification: ruff / mypy / lint-imports clean; interrogate 94.3%; pytest
  `216 passed, 5 deselected` (210 unit + 6 new SSE integration).

**Deviations:**
- `sse-starlette` is not on the project deps path → fell back to plain
  `StreamingResponse` with explicit SSE headers (matches plan §2 fallback). No
  runtime cost; Cloud Run behaviour identical with `X-Accel-Buffering: no`.
- `_triage_event_stream` terminates the stream with a bare `yield done` after the
  `try/except Exception` (not inside `finally:`) — yielding from `finally` after a
  `GeneratorExit` (raised by `aclose()`) raises `RuntimeError`. With the current
  shape, `CancelledError` propagates up, `done` is skipped (consumer is gone anyway).
- I-10 test is minimal — asserts the client can close mid-stream without the
  server-side coroutine raising into the test body. Deeper "server cleanup observed"
  assertions deferred to Day 5 when `audit_event` / logging hooks provide a signal.
- `audit_event` NOT wired from the route yet — stays at Day 5 per plan footgun #6
  (correlation_id middleware still pending).

**Open for Day 5:**
- Add `audit_event` emissions in the route handler (correlation_id + user_id + company_id
  from `CurrentUser`).
- slowapi rate limit `@limiter.limit("10/minute")` on the triage route.
- `tenacity` retry on Impact fetchers (tool-level, not whole agent).
- OTel spans over the SSE stream. No refactor of Day 4 code expected.

---

## Day 5 — 2026-04-23 (planned)

**Planned:**
- `POST /api/v1/auth/onboard`
- `GET /api/v1/exceptions`
- slowapi middleware on `/triage` + `/auth/onboard`
- OTel + Cloud Trace wiring (`core/tracing.py`)
- `audit_event` emissions at call sites
- `tenacity` retry on Impact (`utils/llm_retry.py`)
- `max_output_tokens` settings
- Tests U-19 … U-27, I-12 … I-15
- Atomic commits per concern
- **Billing upgrade on `sct-prod` to Gemini Tier 1 paid.**

**Actuals:** (to be filled)

---

## Day 6 — 2026-04-24 (planned)

**Planned:**
- Rewrite `infra/firestore.rules` per `firestore-utilization-audit-tier1.md` §7
- Rewrite `infra/firestore.indexes.json` per §8
- `firebase deploy --only firestore:rules,firestore:indexes` to `sct-dev` first, then `sct-prod`
- `scripts/seed_all.py` consolidated seeder
- Populate `companies.json`, `users.json`, `festival_calendar.json` with full content (§10)
- Fix `get_affected_shipments` tenant filter (U-34 regression)
- Wire `triage_results/{id}` + `audit_events/{id}` writes in `runners/triage_runner.py`
- Tests U-28 … U-35
- Atomic commits per concern

**Actuals:** (to be filled)

---

## Day 7 — 2026-04-25 (planned)

**Planned:**
- Classifier evalset 15 cases via `adk web` capture-then-edit
- Impact evalset 10 cases
- `adk eval` runs; prompt iteration if below thresholds (budget: 2-3 tweak rounds)
- **Start UI work** (framework committed by now)

**Actuals:** (to be filled)

---

## Day 8 — 2026-04-26 (planned)

**Planned:**
- Finish UI: Landing + Triage console + History
- Staging deploy to `sct-staging`: `gcloud run deploy`
- Firebase Hosting rewrite config
- Smoke test on staging URL
- SSE-specific Cloud Run debugging if any

**Actuals:** (to be filled)

---

## Day 9 — 2026-04-27 (planned)

**Planned:**
- Prod deploy to `sct-prod` with `min-instances=1`
- Set `--timeout=3600`, `--service-account=sct-prod-runtime`, `--set-secrets`
- Full dress rehearsal with all 3 flagship scenarios
- Last-mile fixes
- Release commit

**Actuals:** (to be filled)

---

## Day 10 — 2026-04-28 (planned)

**Planned:**
- Morning pre-submit smoke test
- Submit demo URL
- Final update to `impl-log.md` + `test-report.md`
- Sprint retrospective in `retro.md`

**Actuals:** (to be filled)

---

## Key decisions captured during build

(Fill as decisions arise — e.g. framework pick, any cut-line activations, any scope swaps.)

## Surprises + learnings

(Fill at end of sprint.)

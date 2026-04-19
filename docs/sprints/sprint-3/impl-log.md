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

## Day 4 — 2026-04-22 (planned)

**Planned:**
- `runners/triage_runner.py` streaming path (`_triage_event_stream`)
- `runners/routes/triage.py` (`POST /api/v1/triage`)
- `tests/integration/test_triage_sse.py` (I-8 … I-11)
- Atomic commit

**Actuals:** (to be filled)

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

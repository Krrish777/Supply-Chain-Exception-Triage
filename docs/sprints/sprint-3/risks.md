---
title: "Sprint 3 Risks — Pre-mortem"
type: risk-assessment
sprint: 3
last_updated: 2026-04-18
status: approved-pending-user
supersedes: "./risks-v1-archived.md"
---

# Sprint 3 Pre-mortem

Imagine it's Apr 29 and Sprint 3 failed. What happened?

---

## 1. Top 10 failure modes

### R-1 — Gemini 429 quota hit during demo (HIGH likelihood × HIGH impact)

**Scenario:** Judge clicks scenario → pipeline starts → Classifier 429 on first call. Retry fails. Demo frozen.

**Mitigations:**
- Upgrade `sct-prod` project to Gemini Tier 1 paid (confirm billing + tier by Day 5 — 2026-04-23). Free tier (5-15 RPM) is insufficient.
- `tenacity` retry with exp backoff + jitter, 3 attempts.
- Budget alerts $10/$25/$50 so we notice overspend mid-week, not mid-demo.
- Emergency kill-switch documented in `llm-quotas-rate-limits.md` §13: (1) bump tier in console, (2) flip to Vertex AI `asia-south1`, (3) mock-mode (not implemented — chosen user decision was "live or nothing", so this option is off the table).
- User explicitly chose no-fallback: "live or nothing." Means mitigations must hold.

**Signal to watch:** any 429 in dress rehearsal → stop demo prep, investigate, adjust quota BEFORE Apr 28.

### R-2 — SSE breaks on Cloud Run (MEDIUM × CRITICAL)

**Scenario:** SSE works locally. On Cloud Run, frames buffer, client sees nothing for 30s, then dump. Judge confusion.

**Mitigations:**
- Headers per `fastapi-sse-api-design.md` §2: `Cache-Control: no-cache`, `X-Accel-Buffering: no`, `Connection: keep-alive`, `Content-Type: text/event-stream`.
- Cloud Run `--timeout=3600` to allow long streams.
- Day 8 (Apr 26) dedicated to Cloud-Run-specific SSE debugging; deploy early to staging to catch.
- Heartbeat `:` comment every 15s prevents proxy timeouts.

**Signal:** staging SSE test fails on Apr 26 → stop UI work, fix SSE first.

### R-3 — Evalset doesn't hit thresholds (MEDIUM × MEDIUM)

**Scenario:** Classifier 10/15 pass, not 13/15. Impact 6/10, not 8/10. Gate fails.

**Mitigations:**
- Rubric-based scoring (not exact-match) tolerates wording drift.
- `num_runs=3` mitigates nondeterminism.
- Prompt iteration budget: Day 7 (Apr 25) has slack for 2-3 prompt tweak rounds.
- Cut-line: demote evalset thresholds to advisory if Day 8 comes and we're still below.

**Signal:** Day 7 end-of-day < 11/15 classifier or < 7/10 impact → trigger cut-line discussion.

### R-4 — Custom-claim refresh bug (MEDIUM × HIGH)

**Scenario:** Judge signs in, `/auth/onboard` sets claims, but frontend doesn't force-refresh the ID token. Next API call fails with missing `company_id` claim. 403.

**Mitigations:**
- `firebase-auth-oauth-multitenancy.md` §9 explicit: `user.getIdToken(/* forceRefresh */ true)` AFTER onboard response.
- Integration test I-14 asserts round-trip.
- Full dress rehearsal on Apr 27 catches this.

**Signal:** any "missing company_id claim" log on staging → fix before prod deploy.

### R-5 — Tenant leak via `get_affected_shipments` (LOW × CRITICAL if unfixed)

**Scenario:** Current tool queries Firestore without `company_id` filter. Tenant A can see tenant B's shipments.

**Mitigations:**
- Day 6 explicit fix with regression test (U-34, U-35).
- Firestore rules are a secondary defense but not primary — rules allow read by any authed member, tool must filter.
- Integration test I-7 asserts cross-tenant isolation.

**Signal:** U-34 or I-7 fails → block merge of Day 6 commit.

### R-6 — UI framework decision slips (MEDIUM × MEDIUM)

**Scenario:** Day 7 starts, user hasn't decided UI framework. UI work can't begin. Pipeline into deploy squeezed.

**Mitigations:**
- Day 1 raises the question again.
- PRD §9 explicitly flags as open item.
- If still undecided by Day 5: pre-commit to Next.js + TypeScript + shadcn + Firebase Hosting (my pre-advised default).

**Signal:** Day 5 ends without decision → force-pick Next.js and proceed.

### R-7 — Cloud Run cold start + min-instances billing surprise (LOW × LOW)

**Scenario:** `min-instances=1` for 48h costs more than expected. Or we forget to turn it off after demo.

**Mitigations:**
- Cost projection in `gcp-proper-utilization.md` §19 — ~$8 total demo window.
- Budget alerts catch overshoot.
- Post-demo checklist: `gcloud run services update --min-instances=0` on Apr 29.

**Signal:** budget alert at $25 during demo week → investigate.

### R-8 — Firestore composite index build time (LOW × MEDIUM)

**Scenario:** `firebase deploy --only firestore:indexes` takes 20min on prod for the 12 new indexes. `GET /api/v1/exceptions` fails during the build window.

**Mitigations:**
- Deploy indexes Apr 24 (Day 6), not Apr 27.
- Dry-run on staging first to learn timing.
- Cloud Console shows build progress.

**Signal:** any "index not ready" error after Apr 26 → wait or route around.

### R-9 — Test writing eats feature time (MEDIUM × MEDIUM)

**Scenario:** 25+ new unit tests + integration tests + 25 eval cases take longer than Day 2-7 budget allows. Sprint slips.

**Mitigations:**
- Atomic commits — each feature includes its own tests. Tests are not a separate work item.
- Tests informed by Given/When/Then list in `test-plan.md` — less ideation time.
- Cut-line: Impact evalset first to defer if needed.
- `adk eval` cases can be partially captured from `adk web` sessions (capture-then-edit pattern).

**Signal:** Day 4 end and < 10 new unit tests in → replan.

### R-10 — Judge tries something we haven't rehearsed (MEDIUM × HIGH)

**Scenario:** Judge pastes Chinese text, or 20k characters, or empty input. Pipeline crashes or returns garbage.

**Mitigations:**
- `max_output_tokens` caps runaway generation.
- Input size cap: reject > 20k chars at API layer (422).
- Classifier low-confidence path → graceful `requires_human_approval` response.
- UI shows the "pipeline is live but input is unusual" message gracefully, not a stack trace.
- Day 7 dress rehearsal includes 2-3 adversarial "what if the judge does X" runs.

**Signal:** dress-rehearsal stress test crashes → add graceful path.

---

## 2. Schedule risk register

| Day | Risk | Mitigation |
|---|---|---|
| Day 1 (Apr 19) | LLM commit breaks tests | Run full pytest before the commit lands |
| Day 3 (Apr 21) | Pipeline factory has subtle bug that passes unit tests but fails integration | Integration test is the same-day deliverable, not next-day |
| Day 5 (Apr 23) | Rate-limit middleware breaks existing tests | Scoped to `/api/v1/triage`, not global; verify against existing classify/impact routes |
| Day 6 (Apr 24) | Firestore rules rewrite breaks existing integration tests | Rules emulator tests added same day |
| Day 7 (Apr 25) | Evalset capture takes 3 hours per agent | Budget Day 7 for 4 hours total; cut to 10 classifier + 6 impact if we blow budget |
| Day 8 (Apr 26) | Staging deploy reveals an env-var or secret misconfiguration | `gcp-proper-utilization.md` §17 pre-deploy checklist |
| Day 9 (Apr 27) | Prod deploy has surprise (cold start visible, quota, auth) | 24h of staging soak gives us time to surface these |

---

## 3. Pre-mortem conclusion

Most likely failure: **quota or SSE issue revealed on Apr 27 dress rehearsal with no time to fix.** Mitigation is to surface both issues earlier — staging deploy Apr 26 with SSE + real Gemini calls.

Second most likely: **evalsets slip a threshold** — mitigated by cut-line (demote to advisory) and rubric scoring.

Lowest-likelihood catastrophic: **tenant leak** — mitigated by explicit fix + regression test + rules defense-in-depth.

User's "live or nothing" rollback posture compresses the risk budget. Day 5 billing upgrade + Day 6 staging deploy + Day 7 dress rehearsal are the three load-bearing dates.

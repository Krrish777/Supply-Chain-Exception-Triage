---
title: "Next-Session Handoff — Sprint 3 build"
type: handoff
last_updated: 2026-04-18
---

# Next-Session Handoff — Sprint 3 Build

**Paste this into the first message of the build session.**

---

## Start-of-session prompt

```
Read these files in order before writing any code:

1. docs/sprints/sprint-3/prd.md                 — the trimmed PRD (approved)
2. docs/sessions/2026-04-18-research-session-decisions.md
3. docs/decisions/adr-009-coordinator-pattern.md
4. docs/sprints/sprint-3/test-plan.md
5. docs/sprints/sprint-3/risks.md
6. docs/sprints/sprint-3/security.md
7. docs/research/coordinator-orchestration-patterns.md
8. docs/research/firestore-utilization-audit-tier1.md
9. docs/research/fastapi-sse-api-design.md
10. docs/research/firebase-auth-oauth-multitenancy.md
11. docs/research/llm-quotas-rate-limits.md
12. docs/research/observability-otel-cloud-trace.md
13. docs/research/gcp-proper-utilization.md

Then:

CURRENT STATE:
- Tier 1 deadline: 2026-04-28 (10 days from 2026-04-19 session start).
- Sprint 0, 1, 2 committed. Classifier + Impact live as SequentialAgents.
- `core/llm.py` + Groq+LiteLLM support + tests are UNCOMMITTED in the working tree — commit these first.
- Pre-existing failure in test_classification.py (dict vs list[KeyFact]) — fix in second commit.

DAY 1 ORDER (do these in sequence):
1. Commit LLM work (atomic commit 1).
2. Fix test_classification.py (atomic commit 2).
3. Seed emulator + live-test Impact in `adk web` against NH-48. Screenshot the output.
4. Ask user for UI framework decision (deferred from research session).

SPRINT BUILD ORDER (Days 2-9):
Callbacks → pipeline → runner → SSE → API → auth → Firestore fixes → UI → deploy.
Full day-by-day in docs/sprints/sprint-3/prd.md §5.

EXIT GATE: docs/sprints/sprint-3/prd.md §4 (15 acceptance criteria).
CUT-LINE IF SLIPPING: Impact evalset → History page → evalset thresholds (advisory).
DEMO: Cloud Run URL + dashboard UI + 3 flagship scenarios (NH-48 flagship, FSSAI backup, safety override backup).

RULES TO FOLLOW:
- Atomic commits per feature.
- Each feature ships with tests same day. No test-debt commits.
- All ADK imports only in modules/*/agents/*/agent.py, runners/, modules/*/memory/.
- All ruff + mypy + import-linter must stay green.
- Update docs/sprints/sprint-3/impl-log.md end of each day with actuals + deviations.
- NO web search during build — all research is in docs/research/.
- Follow SDLC: verification (pytest/ruff/mypy/eval) + validation (user review of sample outputs) — both required before claiming a feature done.

Ready to start Day 1?
```

---

## Pre-session checklist (do before starting the build session)

- [ ] Confirm `sct-prod` GCP project exists (or create fresh to claim $300 credits).
- [ ] Confirm Gemini API billing tier — must be Tier 1 paid before Day 5 for rehearsal quota.
- [ ] Budget alerts created at $10 / $25 / $50 on `sct-prod`.
- [ ] Firebase project initialized for prod.
- [ ] UI framework choice ready to disclose on Day 1.
- [ ] Full emulator seed script still runs (smoke test).
- [ ] `.env` for local dev has every Settings field (GCP_PROJECT_ID, FIREBASE_PROJECT_ID, FIRESTORE_EMULATOR_HOST, LLM_PROVIDER, LLM_MODEL_ID).

---

## If this session catches fire (cut-line order)

1. Drop Impact evalset (keep Classifier evalset).
2. Drop History page (keep Landing + Triage console).
3. Drop Exception detail page (already deferred).
4. Demote evalset thresholds to advisory.
5. Single-instance Cloud Run, skip Firebase Hosting, serve UI from Cloud Run directly.
6. Only if all above fail: demo locally with a recorded screen capture as submission artifact.

---

## Post-session wrap-up (Day 10 Apr 28)

- [ ] Fill `impl-log.md` with Day 1-10 actuals
- [ ] Fill `test-report.md` with each acceptance criterion ✅/❌ + evidence
- [ ] Run `superpowers:code-reviewer` agent, paste output into `review.md`
- [ ] Write `retro.md` (start/stop/continue)
- [ ] Submit demo URL to hackathon portal
- [ ] Write `docs/sessions/2026-04-28-sprint-3-complete.md` with final decisions + status
- [ ] Update `MEMORY.md` with any new feedback learned during build
- [ ] Disable `min-instances=1` on Cloud Run (Apr 29+) to stop billing

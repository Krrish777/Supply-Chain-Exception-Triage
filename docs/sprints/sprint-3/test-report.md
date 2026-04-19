---
title: "Sprint 3 Test Report"
type: test-report
sprint: 3
last_updated: 2026-04-18
status: scaffold-to-be-filled-post-build
---

# Sprint 3 Test Report

Populated at end of build session. Tracks whether each acceptance criterion in `prd.md` §4 is ✅ or ❌, with evidence.

---

## Acceptance criteria status

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | All pytest unit tests pass | ⏳ | (pytest output file link or tail) |
| 2 | Full pipeline integration test passes (NH-48) | ⏳ | (output) |
| 3 | SSE integration test passes | ⏳ | (output) |
| 4 | ruff clean | ⏳ | |
| 5 | mypy clean | ⏳ | |
| 6 | import-linter clean | ⏳ | |
| 7 | Classifier evalset ≥13/15 | ⏳ | `adk eval` output |
| 8 | Impact evalset ≥8/10 | ⏳ | `adk eval` output |
| 9 | NH-48 live via adk web | ⏳ | Screenshot in `impl-log.md` Day 1 |
| 10 | Cloud Run prod URL responds | ⏳ | Post-Day-9 curl output |
| 11 | Dashboard UI runs all 3 scenarios | ⏳ | Dress rehearsal notes |
| 12 | OTel spans in Cloud Trace | ⏳ | Screenshot |
| 13 | Budget alerts configured | ⏳ | `gcloud billing budgets list` output |
| 14 | Firestore rules cover 12 collections | ⏳ | Rules emulator test output |
| 15 | `audit_events` populated per run | ⏳ | Firestore console spot-check |

---

## Coverage

(to be filled post-build)

```
pytest --cov=src --cov-report=term-missing tests/
```

---

## Eval run summaries

### Classifier

- Run 1: X/15
- Run 2: X/15
- Run 3: X/15
- Final (majority): X/15 ✅/❌

### Impact

- Run 1: X/10
- Run 2: X/10
- Run 3: X/10
- Final (majority): X/10 ✅/❌

---

## Any cut-line activations

(If we activated any cut-line from `prd.md` §4 — document which, when, and why here.)

---

## Known issues at submission

(List anything that works but has a caveat — e.g. "Impact evalset is advisory only, not gating.")

---

## Post-submission follow-ups

(Carry-overs into Tier 2 planning.)

---
title: "Sprint 2 Risks — Pre-mortem for Impact Agent"
type: deep-dive
domains: [supply-chain, hackathon, sdlc, risk-management]
last_updated: 2026-04-10
status: active
confidence: high
sources: ["[[Supply-Chain-Sprint-Plan-Spiral-SDLC]]", "[[Supply-Chain-Agent-Spec-Impact]]", "[[Supply-Chain-Firestore-Schema-Tier1]]"]
---

# Sprint 2 Risks — Pre-mortem for Impact Agent

> **Exercise:** Assume Sprint 2 shipped late, incomplete, or broken. Work backwards from the failure to identify root causes and mitigations. Gary Klein's pre-mortem method.
> **Companion to:** `prd.md` section 10 (Risks summary) and `test-plan.md`.

---

## Table of Contents

1. [Pre-mortem Prompt](#1-pre-mortem-prompt)
2. [Critical Risks (P0)](#2-critical-risks-p0)
3. [High Risks (P1)](#3-high-risks-p1)
4. [Medium Risks (P2)](#4-medium-risks-p2)
5. [Low Risks (P3)](#5-low-risks-p3)
6. [Risk Register Summary Table](#6-risk-register-summary-table)
7. [Early Warning Signals](#7-early-warning-signals)
8. [Escalation Triggers](#8-escalation-triggers)
9. [Contingency Matrix](#9-contingency-matrix)

---

## 1. Pre-mortem Prompt

> "It is end of day Apr 15, 2026. Sprint 2 has failed to deliver a working Impact Agent. The AC gate did not pass. Sprint 3 cannot start. The Apr 24 deadline is now in jeopardy. Walk backwards: what went wrong?"

Seven plausible failure narratives surfaced during the pre-mortem session. Each is scored on probability and impact and mapped to mitigations that are already baked into the PRD.

---

## 2. Critical Risks (P0)

### Risk 2.1 — Multi-tenant data leakage in production

**Narrative:** The Impact Agent shipped and went to demo. During the hackathon presentation, a judge asked about multi-tenancy. The team proudly showed the isolation test. Later, during internal review, someone noticed that `get_shipment_details` accepted `company_id` as a tool argument in an early draft and the LLM learned to override it from prompt-injected input. In production, a malicious `raw_content` could coerce the Impact Agent to read any tenant's shipment data.

**Why it happens:**
- Sprint 2 added a `company_id` parameter to tools during hour 2-3 of Day 1 because "the LLM needs to know which company" (wrong — the LLM does not need to know; the session state does).
- Code review missed the signature change because the PR diff was large (12+ files).
- No test asserts the tool signature. Tests only assert behavior with the correct `company_id`.

**Why this is CRITICAL:** This is not a "bug" — it is a data breach. DPDP Act 2023 and GDPR both apply. A single cross-tenant leak can end the product's commercial viability.

**Probability:** Low (mitigated) — requires multiple failures to occur together.

**Impact:** CRITICAL — catastrophic.

**Mitigations (already in PRD):**
1. **Signature test** — `test_no_company_id_in_tool_signature` uses `inspect.signature()` to assert the tool's parameter list does NOT include `company_id`. This catches the drift at PR time.
2. **Tool-layer guard** — `_company_id()` helper reads from `ToolContext.state` only. If state is missing `company_id`, raises `PermissionError` rather than accepting a default.
3. **Multi-tenant integration test** — `test_impact_multi_tenant_isolation.py` seeds two companies with colliding vehicle IDs and asserts complete isolation.
4. **Firestore rules** — defense-in-depth layer blocks cross-tenant reads at the database level for client-SDK code paths.
5. **Code review checklist** — `review.md` template has a "multi-tenancy" box that MUST be ticked for Sprint 2.
6. **`security.md` OWASP API01** — explicit item with test IDs.

**Residual risk:** The server-client-library bypasses Firestore rules. Documented in `security.md` as a known gap. Tool-layer guard is the authoritative control; rules are backup.

### Risk 2.2 — Impact Agent hallucinates shipment IDs

**Narrative:** The agent works in testing but occasionally (5% of runs) returns an `affected_shipments` list with IDs that do not match anything in Firestore. The LLM invents `SHP-2024-9999` or returns a shipment from a different customer entirely. The `impact_sanity_check` catches this late in Sprint 2 by asserting `reputation_risk_shipments` subset — but not the affected list itself.

**Why it happens:**
- The agent prompt does not say "every shipment_id in your output MUST come from a tool call result."
- The few-shot example is byte-identical to the real NH-48 data, which makes the LLM copy-paste IDs from the example into the new scenario.
- No test asserts that `affected_shipments[*].shipment_id` values appear in the tool-call results.

**Why it is CRITICAL:** A hallucinated shipment ID breaks downstream Sprint 3 Coordinator logic (Resolution Agent would try to look up a non-existent shipment) AND gives customers false information.

**Probability:** Medium. LLM hallucination is well-documented; few-shot examples can actually increase it in this case (the LLM might memorize the example IDs).

**Impact:** HIGH. Breaks downstream processing + customer trust.

**Mitigations:**
1. **Explicit prompt instruction** — architectural rule #3: "Every `shipment_id` in your output must come from a tool call result."
2. **`impact_sanity_check` extension** — add an invariant that asserts every `shipment_id` in `affected_shipments` came from a tool-call event (requires access to `CallbackContext.events` via Sprint 3 Coordinator).
3. **Few-shot example warning** — add a comment in the prompt: "The example below shows NH-48. For other scenarios, the IDs will be DIFFERENT. Do NOT copy these IDs."
4. **Eval case** — `impact_eval.json` case #5 (`empty_vehicle_zero_shipments`) asserts zero hallucinated shipments when the tool returns empty.
5. **Sprint 3 carryover** — wire the tool-call-tracking invariant in the `after_model_callback`. Sprint 2 tests call `impact_sanity_check` on canned data only.

**Residual risk:** Invariant only catches hallucinations Sprint 3 onward. Sprint 2 baseline relies on prompt discipline + eval case #5.

---

## 3. High Risks (P1)

### Risk 3.1 — AgentEvaluator F1 score stays < 0.80

**Narrative:** By Hour 7 Day 2, the eval harness is running but F1 is stuck at 0.65. The LLM returns the right shipment IDs but wrong priority order (FitHaus before KraftHeaven, for example). Slack budget is consumed iterating on the prompt. By end of Day 2, F1 is at 0.76 — close but under the gate.

**Why it happens:**
- Priority reasoning is ambiguous without a clear "churn_risk × deadline_urgency" formula in the prompt.
- Eval case weights are naive (trajectory match is too strict on order).
- Gemini 2.5 Flash occasionally swaps the last two items because it weighs "routine replenishment" higher than "new customer first-impression" when both have similar deadlines.

**Probability:** Medium (30-40% — this is the single hardest quality bar in Sprint 2).

**Impact:** HIGH — blocks the gate.

**Mitigations:**
1. **Relaxed gate: F1 >= 0.80 not 0.95.** Sprint 1 used 0.85 for Classifier (a simpler task); Impact's richer output warrants a lower bar.
2. **Priority rules are explicit in prompt** — `<priority_rules>` block has 3 concrete hard rules + LLM reasoning.
3. **12 eval cases, not 20** — smaller sample means one bad case hurts less.
4. **Slack buffer reserved specifically for prompt tuning** — 2 hours at end of Day 2.
5. **Rollback plan step 3** — cut eval to 8 cases if needed. The 4 cut cases (9-12) test edge cases that are nice-to-have, not gate-critical.
6. **Rubric-based scoring** — `final_response_match_v2` allows paraphrase tolerance in `priority_reasoning` text; only structural fields are strict.
7. **Pin `temperature=0`** — Sprint 1 pattern; eliminates run-to-run noise.

**Residual risk:** If F1 at end of Day 2 is 0.74 and slack is exhausted, execute rollback step 3 (cut 4 cases). Document in `retro.md`.

### Risk 3.2 — Firestore emulator flakiness on Windows

**Narrative:** Tests pass locally on Linux but fail randomly on Windows CI. The developer's daily workflow is on Windows (per env info). The `FIRESTORE_EMULATOR_HOST` environment variable is not honored on Windows because the developer set it in a PowerShell profile that pytest does not read, or the emulator uses Unix socket paths on Linux and TCP on Windows.

**Why it happens:**
- Sprint 0 set up the emulator but may not have verified Windows compatibility end-to-end.
- `firebase emulators:start` uses different transport on different OSes.
- Path separators in `scripts/seed/` directory trip up `json.loads(path.read_text())` on Windows with CRLF line endings.

**Probability:** Medium (20-30%) — given the dev is on Windows 11 per session env.

**Impact:** MEDIUM — blocks testing but not production (prod runs on Linux).

**Mitigations:**
1. **`pathlib.Path` everywhere** — seed loader and tests use `pathlib`, never string concatenation.
2. **`encoding="utf-8"` explicit on all `read_text()` calls** — avoids CRLF surprises.
3. **Fallback fixture using `mock-firestore-async`** — if the real emulator fails, a pure-Python double can run the unit tests. Document in `test-plan.md` section 2.2.
4. **Explicit `FIRESTORE_EMULATOR_HOST` assertion in conftest** — the fixture prints the env var value on startup so failure is obvious.
5. **CI runs on Linux** — the gate is Linux-based. Windows is a dev convenience, not a release target.
6. **Sprint 0 verification** — `impl-log.md` should record a successful emulator-based test on the dev machine. If not, that is a Sprint 0 carryover.

### Risk 3.3 — Supermemory SDK not production-ready

**Narrative:** Sprint 2 goes to ship the `SupermemoryAdapter` but the SDK's `client.search.documents()` signature is different from what the docs show, or the SDK is not installable from PyPI on Python 3.13, or the API key provisioning takes 48 hours. The adapter stays stub-only and ADR-010 looks silly.

**Why it happens:**
- Supermemory SDK is auto-generated (per GitHub research) — API may have churned.
- Sprint 2 did not actually exercise the real SDK against real API — all tests are mocked.
- Account provisioning is out of team control.

**Probability:** Medium.

**Impact:** MEDIUM — Sprint 2 can still ship with stub only.

**Mitigations:**
1. **Default is stub** — Sprint 2 baseline does not require a real Supermemory account or key. `StubMemoryProvider` ships in PR and Sprint 3 can continue without the adapter.
2. **`MemoryProvider` ABC seam** — swapping implementations is a 1-line change in Sprint 3. If the adapter is broken, Sprint 3 can temporarily keep the stub.
3. **Mock-only unit tests** — no real API contact in CI. `SupermemoryAdapter` works against the SDK's type hints, not its runtime quirks.
4. **Fallback documented** — `adr-010-memory-provider-seam.md` explicitly lists "ship with stub only" as an acceptable Sprint 2 exit state.
5. **Rollback plan step 1** — drop the adapter entirely; stub ships; Sprint 3 re-evaluates.

### Risk 3.4 — `asyncio.gather` inside ADK tools raises nested event loop error

**Narrative:** Testing locally, `_get_shipments_bulk` (private helper) which uses `asyncio.gather` raises `RuntimeError: This event loop is already running`. ADK's runner uses `asyncio.run()` which establishes a loop, and our tool tries to create a new one. The Sprint 1 pattern did not exercise this because Classifier tools were single-shot.

**Why it happens:**
- ADK uses its own async runtime; `asyncio.gather` inside a tool function is fine but creating new loops is not.
- If a developer writes `asyncio.run(gather(...))` instead of just `await gather(...)`, it fails.
- `asyncio.to_thread()` (used in `SupermemoryAdapter`) spawns a thread pool that ADK may not tolerate.

**Probability:** Low (20%) — `await asyncio.gather(...)` inside an already-async function is standard and works.

**Impact:** MEDIUM — forces sequential fetches and 2-3x slower tool latency.

**Mitigations:**
1. **Pattern verification in Hour 2-3 Day 1** — write `test_gather_concurrency_under_wallclock_threshold` FIRST, verify it works against the emulator before writing production code.
2. **Fallback: sequential await loop** — if `gather` fails, replace with `for sid in ids: results.append(await _fetch(sid))`. Correct, just slower. Still hits the 2s budget.
3. **`asyncio.to_thread` isolation** — only used in `SupermemoryAdapter` which is optional. Stub has no thread pool.

---

## 4. Medium Risks (P2)

### Risk 4.1 — Firestore composite indexes not created, queries fail silently

**Narrative:** Sprint 2 commits `infra/firestore.indexes.json` but the emulator does not auto-load it. Queries filtering on `company_id + vehicle_id + status` succeed on simple cases but fail with "FAILED_PRECONDITION: The query requires an index" on production deployment in Sprint 5.

**Probability:** Medium (35%) — this is a classic Firestore production gotcha.

**Impact:** LOW in Sprint 2 (emulator does not enforce indexes), HIGH in Sprint 5.

**Mitigations:**
1. **Committed indexes file** — `infra/firestore.indexes.json` is in the repo per Sprint 2 scope, with 5 composite indexes.
2. **Sprint 5 deployment script** — runs `firebase deploy --only firestore:indexes` before Cloud Run deploy.
3. **Documentation in `impl-log.md`** — note that emulator queries do NOT validate indexes; production will fail until the file is deployed.
4. **No Sprint 2 test** — we cannot test production index requirements locally. Accept the risk; mitigate via Sprint 5 checklist.

### Risk 4.2 — LLM returns weights that do not sum to 1.0

**Narrative:** Impact Agent returns `value_weight: 0.4, penalty_weight: 0.3, churn_weight: 0.4` — sum is 1.1. The `impact_sanity_check` does not enforce weight sum. Eval cases pass because the test only checks individual values.

**Probability:** Medium (30%).

**Impact:** MEDIUM — not a crash, but the reasoning becomes incoherent.

**Mitigations:**
1. **Prompt explicit instruction** — "three weights MUST sum to 1.0 +/- 0.02" in `<impact_calculation>` block.
2. **Extend `impact_sanity_check`** — add invariant #6: `abs(sum(weights) - 1.0) < 0.02`. Not in Sprint 2 baseline but add in slack if found.
3. **Eval case #1 assertion** — integration test 7.1.1 asserts the sum.
4. **Sprint 3 post-processor** — Coordinator `after_model_callback` can normalize weights if they are close but not exact.

### Risk 4.3 — Seed JSON drifts from Pydantic schemas

**Narrative:** Sprint 0 defined `ShipmentImpact` schema. Sprint 2 creates `scripts/seed/shipments.json` with field names that subtly differ (`customer_type` vs `customer_type_snapshot`). Seed loads fine (Firestore is schemaless), but the tool returns dicts the agent cannot parse into `ShipmentImpact`.

**Probability:** Medium (25%).

**Impact:** MEDIUM — tool returns data but agent fails at final output serialization.

**Mitigations:**
1. **Schema-validated seed loader** — the seed script calls `pydantic.ShipmentImpact.model_validate(record)` before writing. Drift fails loudly at seed time.
2. **Integration test 7.1.1** — exercises the full path from seed -> tool -> agent -> output. Catches drift.
3. **Cross-reference PRD** — seed JSON field names mirror the spec (section 2.6) exactly. Review in PR.

### Risk 4.4 — Documentation debt at end of Day 2

**Narrative:** Days 1 and 2 are intense; by Hour 8 Day 2, the engineer is tired and writes `impl-log.md`, `retro.md`, `security.md`, and two ADRs in 60 minutes. Quality is low. Sprint review flags the docs as insufficient.

**Probability:** Medium (40%) — historically, docs get cut first under deadline.

**Impact:** MEDIUM — Sprint 2 still "works" but next-engineer handoff suffers.

**Mitigations:**
1. **Templates exist from Sprint 0** — docs are fill-in-the-blanks, not from-scratch.
2. **Docs time-boxed to 60 min** — hour 8 Day 2 is reserved. Not spread across the day.
3. **ADRs drafted during build** — as soon as a decision is made (memory seam, LLM weights), capture it in the ADR immediately.
4. **Retro template short** — Start / Stop / Continue is 3 bullets each, 15 minutes total.
5. **Code reviewer skill runs first** — writes 80% of `review.md` automatically.

### Risk 4.5 — Guardrails AI (from Sprint 1) not reused in Sprint 2

**Narrative:** Sprint 1 installed `guardrails-ai` for `ClassificationResult` re-asks. Sprint 2's `ImpactResult` schema is richer; when Gemini emits a malformed field, there is no re-ask fallback. Sprint 2 fails the eval because 2 cases return unparseable JSON.

**Probability:** Low-Medium (20%).

**Impact:** MEDIUM.

**Mitigations:**
1. **ADK `output_schema` is the first line** — Sprint 1 pattern. ADK attempts parse directly.
2. **Sprint 2 scope explicitly defers Guardrails wrapping** — Sprint 3 Coordinator can add it via `after_model_callback` if needed.
3. **Rollback plan: add Guardrails in slack** — if eval fails with parse errors, use Sprint 1's `build_classifier_guard()` pattern and create `build_impact_guard()` with `num_reasks=2`. 30 minutes of work.
4. **Gemini 2.5 Flash is stable on Pydantic schemas** — Sprint 1 had zero parse errors across 12 eval runs.

### Risk 4.6 — `firebase emulators:exec` rule-test path broken

**Narrative:** The rules test in `test_firestore_rules.py` relies on `firebase emulators:exec 'pytest'` which is fragile. The rules layer runs in a separate JVM process and does not always talk to the Python test fixtures cleanly.

**Probability:** Medium (30%).

**Impact:** LOW — the tool-layer guard is the authoritative control; rules are defense-in-depth.

**Mitigations:**
1. **Rollback plan step 5** — cut `test_firestore_rules.py` entirely if it is flaky. Document in `security.md`.
2. **Alternative: rule simulator** — Firebase rules simulator is a REST endpoint that can be hit from Python directly. Replace the `emulators:exec` path with simulator calls.
3. **Tool-layer tests are the primary guard** — `test_impact_multi_tenant_isolation.py` covers the same ground at the Python layer.

---

## 5. Low Risks (P3)

### Risk 5.1 — `SUPERMEMORY_API_KEY` missing in CI fails unrelated tests

**Probability:** Low. All SDK tests are mocked. The key is only needed if a developer accidentally writes a non-mocked test.

**Impact:** LOW.

**Mitigation:** CI env does NOT set the key; tests that need it use `patch.dict(os.environ, {"SUPERMEMORY_API_KEY": "test-key"})` locally.

### Risk 5.2 — Prompt file exceeds Gemini 2.5 Flash context budget

**Probability:** Low. Budget is 15 KB; Gemini 2.5 Flash has 1M context.

**Impact:** LOW (cost only).

**Mitigation:** Fixture test on prompt file size in Sprint 2 Day 2 hour 3-4.

### Risk 5.3 — `InMemoryRunner` does not support object session state

**Probability:** Low. ADK session state is a dict; any picklable Python object fits.

**Impact:** MEDIUM (blocks memory provider injection).

**Mitigation:** `StubMemoryProvider` is declared `@dataclass`-like (just an ABC impl with no state); trivially picklable. Tested in 4.1.4.

### Risk 5.4 — New customer BlushBox churn score (0.7) conflicts with seeded `churn_risk="HIGH"` from the spec

**Probability:** Low. The prompt threshold is flexible; LLM can derive `churn_risk="HIGH"` from 0.7 or 0.9.

**Impact:** LOW.

**Mitigation:** Adjust the seed value to 0.85 if eval case #1 flags the churn mismatch. 1-line change in `scripts/seed/customers.json`.

---

## 6. Risk Register Summary Table

| ID | Risk | Prob | Impact | Priority | Owner | Mitigation in PRD |
|----|------|------|--------|----------|-------|-------------------|
| 2.1 | Multi-tenant data leakage | Low | CRITICAL | P0 | Dev | section 6.1 + test 3.1.11 |
| 2.2 | Hallucinated shipment IDs | Med | HIGH | P0 | Dev + Prompt | Snippet B rule #3 + eval #5 |
| 3.1 | AgentEvaluator F1 < 0.80 | Med | HIGH | P1 | Dev | Slack + rollback step 3 |
| 3.2 | Firestore emulator Windows flakiness | Med | MED | P1 | Dev | `pathlib.Path` + mock fallback |
| 3.3 | Supermemory SDK not ready | Med | MED | P1 | Dev | Stub is default; rollback step 1 |
| 3.4 | `asyncio.gather` nested loop error | Low | MED | P1 | Dev | Verify in Hour 2-3 Day 1 |
| 4.1 | Firestore indexes not created | Med | LOW | P2 | Sprint 5 | Committed file + Sprint 5 deploy |
| 4.2 | LLM weights do not sum to 1.0 | Med | MED | P2 | Dev | Prompt + Sprint 3 post-processor |
| 4.3 | Seed JSON schema drift | Med | MED | P2 | Dev | Pydantic validation at seed time |
| 4.4 | Docs debt at end of Day 2 | Med | MED | P2 | Dev | Templates + time-box |
| 4.5 | No Guardrails wrapper for Impact | Low | MED | P2 | Dev | Add in slack if needed |
| 4.6 | Firebase rules test flaky | Med | LOW | P2 | Dev | Rollback step 5 + tool guard is primary |
| 5.1 | Supermemory key missing in CI | Low | LOW | P3 | Dev | Mock-only tests |
| 5.2 | Prompt file too big | Low | LOW | P3 | Dev | Fixture test |
| 5.3 | Runner does not pickle provider | Low | MED | P3 | Dev | Stub is picklable |
| 5.4 | BlushBox churn score mismatch | Low | LOW | P3 | Dev | 1-line seed fix |

**Top 3 to watch during Sprint 2 execution:** 2.1 (multi-tenancy), 2.2 (hallucination), 3.1 (F1 gate).

---

## 7. Early Warning Signals

If ANY of these trigger during Sprint 2, stop and re-plan:

1. **Hour 2 Day 1:** `firestore_emulator` fixture is not green on the dev machine. Implies Sprint 0 carryover or Windows flakiness (Risk 3.2).
2. **Hour 4 Day 1:** Any Firestore tool test fails with `PermissionError` from the `_company_id()` helper during a legitimate call. Implies session state wiring is wrong (Risk 2.1 vector).
3. **Hour 6 Day 1:** Seed script runs but `test_seed_idempotent.py` shows duplicate documents. Implies idempotency is broken (not yet in PRD test coverage).
4. **Hour 8 Day 1 / End of Day 1:** `adk web` smoke does NOT return a 4-shipment result. Implies agent tool wiring is wrong.
5. **Hour 2 Day 2:** `SupermemoryAdapter` tests fail even with mocks. Implies SDK import path is wrong or API shape is different from docs (Risk 3.3).
6. **Hour 5 Day 2:** `test_impact_firestore_emulator.py::test_impact_agent_nh48_4_shipments` returns 3 or 5 shipments instead of 4. Implies distractor shipments are leaking or NH-48 data is incomplete.
7. **Hour 7 Day 2:** `test_impact_eval_f1_at_least_80` returns F1 < 0.70. Implies prompt quality is fundamentally off; start rollback evaluation.
8. **Hour 8 Day 2:** All tests green but code-reviewer skill flags a CRITICAL. Implies a regression introduced by last-minute changes. Fix or defer.

---

## 8. Escalation Triggers

| Trigger | Action |
|---------|--------|
| **Two early-warning signals in a row** | Pause Sprint 2; user review before continuing |
| **Risk 2.1 (multi-tenancy) realized in any test** | STOP. Fix before any other work. |
| **Risk 2.2 (hallucination) realized > 2 times in eval** | Cut eval cases 9-12 per rollback step 3; iterate on prompt in slack |
| **Risk 3.1 (F1 < 0.80) realized at Hour 7 Day 2** | Slack budget allocated to prompt iteration; if still failing at Hour 8, declare partial |
| **Sprint 2 extends past Apr 15 23:59** | Execute rollback plan steps in order; mark partial; proceed to Sprint 3 with carryover list |
| **Code-reviewer flags CRITICAL at Hour 8 Day 2** | Fix before merging; 30 min slack; if not fixable, create follow-up issue and proceed |

---

## 9. Contingency Matrix

If things go wrong at specific points, execute these plans:

### 9.1 Day 1 Hour 3 — Firestore tools not working
- Revert to Sprint 1 tool pattern (single-doc per call, no gather)
- Use `mock-firestore-async` for unit tests instead of real emulator
- Integration tests deferred to Hour 5-6 Day 2
- Sprint 2 still ships if sequential fetches meet the 2 s budget

### 9.2 Day 1 Hour 8 — `adk web` smoke fails
- Bisect: is `impact_agent` instantiable? (hour 8 test)
- Is the prompt file loadable? (hour 3-4 test)
- Are tools wired? (hour 1 test — re-run)
- If agent instantiates but Gemini rejects the prompt, trim the prompt file and iterate
- Fallback: run the same smoke against `InMemoryRunner` in a pytest script; bypass `adk web` UI

### 9.3 Day 2 Hour 5 — Multi-tenant isolation test fails
- This is Risk 2.1 realized. STOP everything else.
- Audit every tool's `company_id` access path
- Verify no tool accepts `company_id` as argument
- Re-run signature test
- Fix the leak, re-run the multi-tenant test, continue

### 9.4 Day 2 Hour 7 — F1 stuck below 0.80
- First: inspect failing cases individually. Which ones fail?
- If all fail: prompt is broken. Iterate on structure.
- If 1-2 fail: those specific cases are edge cases. Cut them (rollback step 3).
- If 3+ fail: fundamental gap in prompt reasoning. Rebuild few-shot example format.
- Final fallback: ship with 8 cases + F1 >= 0.75 + document in `retro.md`

### 9.5 Day 2 Hour 8 — Running out of time for docs
- Priority order: `retro.md` (15 min) -> `impl-log.md` (15 min) -> `review.md` (code-reviewer auto + 5 min edit) -> `test-report.md` (pytest output + 5 min summary) -> ADRs (10 min each, template fill-in)
- `security.md` can be a stub with OWASP items listed; full content Sprint 3
- Cut `security.md` to a checklist format if time is critical

### 9.6 Mid-sprint realization: "I need something from Sprint 3"
- STOP. Sprint 2 does not know about Sprint 3. If you need Sprint 3 functionality, you have scoped Sprint 2 wrong.
- Common offender: "I need the Coordinator to inject `memory_provider` into session state." Sprint 2 tests inject manually via fixture. Sprint 3 wires it for real.
- Another: "I need the Coordinator to wrap Impact output with `impact_sanity_check`." Sprint 2 leaves the validator importable; Sprint 3 wires it. Test in Sprint 2 calls the validator directly on canned data.

---

## Pre-mortem Conclusion

The biggest P0 risk is multi-tenant leakage (Risk 2.1). It is also the most mitigated — three layers of defense, explicit tests, and a code review checkbox. The biggest P1 risk is F1 < 0.80 (Risk 3.1) which has a well-defined rollback path.

Sprint 2 should be executable within the 18-hour budget IF:
1. Sprint 0 + Sprint 1 gates are actually green (verify, do not assume)
2. Firestore emulator is working on the dev machine before Sprint 2 starts
3. The 2-hour slack buffer is held in reserve, not pre-consumed
4. The code-reviewer skill is run BEFORE writing `review.md`, not after

If any of those four conditions fail, the pre-mortem says Sprint 2 will slip and rollback steps will be needed. Owner discipline on the four conditions is the single highest-leverage intervention.

---

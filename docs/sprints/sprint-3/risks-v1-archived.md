---
title: "Sprint 3 Risks — Pre-mortem for Coordinator Integration Sprint"
type: deep-dive
domains: [supply-chain, hackathon, sdlc, risk-management]
last_updated: 2026-04-10
status: active
confidence: high
sources: ["./prd.md", "./test-plan.md", "[[Supply-Chain-Agent-Spec-Coordinator]]"]
---

# Sprint 3 Risks — Pre-mortem

> **Companion to:** `./prd.md` §10
> **Method:** Gary Klein pre-mortem — assume Sprint 3 failed on Apr 17 at 5 PM and the team is writing the post-mortem at 6 PM. Why did it fail? What early warning would we have caught?
> **Window:** Apr 16 – Apr 17, 2026 (2 days + 2 hr slack)

This document extends the PRD §10 risk table with full narrative, early-warning signals, and mitigation sequencing. Every risk below has at least one detection signal the team can monitor during the sprint.

---

## Risk Framing

Sprint 3 is the **integration sprint** — it assembles the full 3-agent pipeline by wiring Classifier (Sprint 1) + Impact (Sprint 2) under a new Coordinator. The risk profile is dominated by **wiring failures**, not invention failures:

- Most bugs will be in the seams between modules, not in any one module.
- The biggest risk category is "ADK API differs from docs" — because the docs lag behind the 1.x releases.
- The second biggest is "prompt-induced flakiness" — the LLM reasons around rules we thought were explicit.
- The third biggest is "scope creep on Day 2 afternoon" — the slack buffer gets eaten by the eval harness.

---

## R1 — ADK AutoFlow refuses to delegate (description similarity)

**Severity:** High
**Probability:** Medium
**Category:** Framework integration

### Narrative
The Coordinator's LLM generates no `transfer_to_agent` calls despite the prompt instructing delegation. Examination shows both sub-agents' `description` fields overlap heavily ("Specialist agent that classifies supply chain exception events and returns a structured result" vs "Specialist agent that analyzes supply chain exception impact and returns a structured result"). The LLM cannot disambiguate, so it attempts to do classification inline instead of transferring.

### Why it would happen
`[ADK-MA]` explicitly states: *"The calling LlmAgent needs clear instructions on when to transfer, and potential target agents need distinct descriptions for the LLM to make informed decisions."* Sprint 1 and Sprint 2 wrote descriptions independently without cross-checking for overlap.

### Early warning signals
- AC #2 test (`test_sub_agents_wired_with_descriptions`) fails with "3-gram overlap > 50%"
- Day 2 Hour 1 manual `adk web` smoke shows Coordinator producing classification inline instead of delegating
- `coordinator_trace` is empty or contains no transfer events

### Mitigation
1. **Preventive (Day 1 Hour 2)**: Add a test that asserts descriptions share ≤ 50% 3-gram overlap. Fail fast.
2. **Detective**: Day 2 Hour 1 manual smoke run with `adk web` — visually verify the `coordinator_trace` contains 2 transfer events.
3. **Corrective**: Rewrite descriptions to emphasize DIFFERENT dimensions (Classifier: "... classification into a 6-type taxonomy"; Impact: "... blast radius quantification and priority ordering"). Explicit worked example in `coordinator.md` under `## How to Delegate`.
4. **Fallback**: If AutoFlow still refuses, switch to `AgentTool` wrapping (wrap each specialist as a tool). Documented as ADR-012 alternative.

---

## R2 — `before_model_callback` blocks the event loop

**Severity:** Medium
**Probability:** High
**Category:** Async boundary

### Narrative
The ADK callback is synchronous per current docs `[ADK-CB-DOCS]`, but the callback needs to make 4 async Supermemory calls + 2 async tool calls for context injection. The `_run_async` helper uses `asyncio.run_coroutine_threadsafe` to bridge, but inside `adk web` there is no running loop when the callback is invoked on the main thread — `asyncio.run()` is called instead, which fails because an outer event loop is already executing the agent.

### Why it would happen
ADK's threading model for `before_model_callback` is not fully documented. Different ADK versions may run the callback on the main event loop or on a worker thread. Our `_run_async` helper handles both cases but has not been tested against the pinned ADK version.

### Early warning signals
- Day 1 Hour 5–6 unit tests pass but Day 2 manual `adk web` smoke hangs for 10+ seconds then errors
- Stack trace contains `RuntimeError: asyncio.run() cannot be called from a running event loop`
- OR the callback returns before the gather completes, producing empty context blocks

### Mitigation
1. **Preventive (Day 1 Hour 5)**: Write a smoke test that invokes `inject_dynamic_context` from both sync and async contexts. Both must succeed.
2. **Detective**: Day 1 Hour 8 end-of-day `adk web` smoke on NH-48. If context blocks are empty in the rendered prompt, the callback is silently failing.
3. **Corrective (plan A)**: If ADK runs the callback on a worker thread with no running loop → `asyncio.run(coro)` works directly. Remove the `run_coroutine_threadsafe` branch.
4. **Corrective (plan B)**: If ADK runs the callback on the main loop → pre-fetch context in `AgentRunner.run_triage` BEFORE starting the runner, stash results in `session.state["preloaded_context"]`, and the callback just reads from state (no I/O). This is the safer architecture — documented in ADR-013 as the fallback.
5. **Escape hatch**: If both fail → cut dynamic injection entirely and hardcode `<user_context>` for Priya in `coordinator.md`. Rollback item #6 in PRD §13.

---

## R3 — Rule B Safety Override is bypassed by the LLM

**Severity:** Critical
**Probability:** Medium
**Category:** Prompt reliability

### Narrative
The Coordinator's prompt says "scan for safety keywords and short-circuit". An evaluator case feeds "driver was injured, ambulance called" — but the LLM decides the input is really about a truck breakdown and delegates to the Classifier anyway. A safety incident gets classified as a carrier_capacity_failure. This is the worst possible failure mode — it violates the product's safety promise.

### Why it would happen
LLMs are notoriously unreliable at following "do not do X" instructions. Gemini 2.5 Flash may reason "the ambulance is already called, so the safety situation is handled; my job is the logistics triage."

### Early warning signals
- TC-3.1 / TC-3.2 / TC-3.3 fail
- Eval case 02 (Rule B safety Hinglish) fails with a non-safety `final_response`
- `audit_event("runner.safety_override", ...)` is NOT emitted when a safety keyword is present

### Mitigation
1. **Architectural (CRITICAL)**: Rule B is enforced OUTSIDE the LLM in `AgentRunner.run_triage`. The runner calls `check_safety_keywords(event.raw_content)` BEFORE invoking the Coordinator. If positive, the Coordinator is never called at all — the runner returns a `TriageResult` directly. The LLM has no opportunity to reason around it. PRD §12-I documents this.
2. **Preventive**: 3 dedicated integration tests (English / Hindi / Hinglish) using `AssertionError` side effects on sub-agent mocks to prove sub-agents are NEVER invoked.
3. **Detective**: Eval case 02 with `num_runs=3` — if the safety override fires once but not the other two runs, the mitigation has a flake.
4. **Corrective**: Expand the safety keyword list via Sprint 1's `check_safety_keywords` tool; add any missed words to the fixture.
5. **Belt and braces**: The Coordinator's prompt ALSO has Rule B — if the upstream check ever fails, the LLM has a second chance to catch it.

---

## R4 — Cross-tenant leak via Supermemory namespace bug

**Severity:** Critical
**Probability:** Medium
**Category:** Security

### Narrative
`SupermemoryAdapter._namespace(company_id, user_id)` builds `f"sct:{company_id}:{user_id}"`. A developer on Day 1 Hour 3 writes it as `f"sct:{user_id}"` (forgot company_id) during rapid iteration. Tests on Day 1 pass because the seeded stub doesn't simulate multi-tenant data. On Day 2 Hour 7 the cross-tenant test catches it — or, worse, it slips past and lands in Sprint 4.

### Why it would happen
Python f-strings make it easy to drop a variable. The unit tests for Sprint 2's existing methods likely pass even with a bug because Sprint 2 didn't have a multi-tenant fixture.

### Early warning signals
- `test_namespace_rejects_empty` (TC-11.4) passes but only because the typo still raises on empty strings, masking the real issue
- `test_cross_tenant_isolation` (TC-13.2) fails with `SHP-2024-4821 in result.summary`
- Code review flags missing `company_id` parameter usage

### Mitigation
1. **Preventive**: PRD §12-E adapter builds `_namespace` in a single helper with an assertion. Every method call goes through it.
2. **Type safety**: Consider a typed `Namespace` class (dataclass) instead of f-string concatenation — ruff + mypy catch missing fields.
3. **Preventive tests**: TC-10.6 (`test_tenant_bounding_invariant`) explicitly tests a multi-tenant seed.
4. **Detective**: Day 2 Hour 7 runs TC-13.2 — the LAST thing we check before closing the sprint. If it fails, the sprint is BLOCKED.
5. **Code review**: `code-reviewer` skill on the Sprint 3 diff specifically looks for "tenant" and "namespace" patterns.

---

## R5 — ADK eval `response_match_score` stuck at 0.6

**Severity:** High
**Probability:** Medium
**Category:** LLM reasoning quality

### Narrative
`response_match_score` uses ROUGE-1 similarity against the reference `final_response` text. The Coordinator produces a valid summary but phrased differently from the eval reference ("BlushBox campaign in 19h" vs "BlushBox Beauty launch at 10 AM tomorrow"). ROUGE-1 reports 0.6. Sprint 3 AC #12 requires ≥ 0.8.

### Why it would happen
The eval cases are drafted by the engineer, not by observing what the Coordinator actually says. The reference phrasing is ambitious; the LLM is terse.

### Early warning signals
- Day 2 Hour 5 first `test_coordinator_adk_eval` run reports scores in the 0.6–0.7 range
- Individual case failures cluster on cases 01, 07 (the long, detailed summaries)
- `num_runs=3` has high variance (0.5, 0.7, 0.9) — LLM nondeterminism amplifies the issue

### Mitigation
1. **Preventive**: Day 2 Hour 5 budget assumes iteration. Don't lock prompts on Day 1.
2. **Corrective sequence (in order)**:
    a. Rewrite the eval reference texts to be SHORTER and match the Coordinator's natural style (run NH-48 once, copy the actual output, paste as reference).
    b. Add 2 few-shot transfer examples in `coordinator.md` showing the expected summary format.
    c. Lower threshold to 0.75 if only case 07 fails; document in ADR-012 as a known trade-off.
    d. Use `num_runs=5` instead of `num_runs=3` and take the median.
3. **Escape hatch**: Cut the eval harness (Rollback item #1 in PRD §13). Keep only `test_nh48_end_to_end`. Loses rigor but unblocks the sprint gate.

---

## R6 — Context injection sanitization misses a unicode edge case

**Severity:** High
**Probability:** Low
**Category:** Security

### Narrative
A Supermemory `learned_behaviors` entry contains `"</user_context\u200B>"` — a zero-width space between `user_context` and `>`. The regex `</user_context\s*>` matches `\s` (whitespace) but not `\u200B`. The sanitizer lets it through. The LLM sees it as a closing tag and the rest of the learned behaviors becomes system-level context.

### Why it would happen
Regex sanitizers are notoriously incomplete. Unicode has dozens of zero-width / invisible characters that look like whitespace but aren't matched by `\s`.

### Early warning signals
- TC-9.7 (50-string adversarial fuzz) passes — but the fixture doesn't include zero-width chars
- No signal until the vulnerability is exploited in the wild (too late)

### Mitigation
1. **Preventive**: The adversarial fixture MUST include ≥ 10 unicode edge cases (zero-width space, zero-width joiner, RTL override, etc.).
2. **Defense in depth**: After regex sanitization, run `unicodedata.normalize("NFKC", text)` which collapses compatibility-equivalent characters — catches the zero-width trick.
3. **Length cap**: The 2048-char cap limits blast radius. Even if injection slips through, the attacker can't inject a large payload.
4. **Detective**: Add a periodic red-team task to Tier 2 — run actual prompt-injection payloads from known datasets (e.g., `prompt-injection-benchmark`).
5. **Code review**: Explicitly check the sanitizer against OWASP LLM01 guidance.

---

## R7 — Sub-agent failure cascades into Coordinator crash

**Severity:** Medium
**Probability:** Medium
**Category:** Error handling

### Narrative
The Classifier raises `GuardrailsValidationError` because its output failed Pydantic validation twice. The Coordinator's LLM receives the raw exception as a tool error and crashes the agent run. `AgentRunner.run_triage` doesn't catch it and the whole pipeline returns a 500-equivalent.

### Why it would happen
ADK's error propagation for sub-agents is opaque — exceptions may bubble up as events, as exceptions, or as error-flavored LlmResponses depending on the framework version.

### Early warning signals
- TC-13.3 (`test_sub_agent_failure_partial`) fails with an uncaught exception
- Stack trace in the test output instead of a clean `TriageResult(status="partial")`

### Mitigation
1. **Preventive**: `AgentRunner.run_triage` wraps the entire `async for ev in runner.run_async(...)` in `try/except Exception` — any exception becomes `result.status="partial"` with the error in `errors`.
2. **Preventive**: The `try/finally` pattern guarantees session cleanup even on exception.
3. **Detective**: TC-13.3 specifically monkey-patches Classifier to raise and asserts the clean partial-status fallback.
4. **Corrective**: If the test catches something the runner doesn't, expand the exception handler.
5. **Fail-closed semantics**: Per PRD §6.5 — this is the expected behavior, not a workaround.

---

## R8 — Infinite delegation loop

**Severity:** High
**Probability:** Low
**Category:** Agent reliability

### Narrative
The Coordinator's LLM gets into a loop where it transfers to Classifier, Classifier somehow transfers back (because a developer mistakenly added `sub_agents=[coordinator_agent]` to Classifier during Sprint 3 exploration), the Coordinator transfers again, and so on. 30 transfers later, the 30-second timeout fires.

### Why it would happen
Refactoring Sprint 1's `classifier_agent` during Sprint 3 integration could accidentally introduce a cycle. The ADK framework does not prevent cycles at construction time.

### Early warning signals
- TC-1.2 asserts `classifier_agent.sub_agents == []` and `impact_agent.sub_agents == []` — catches it at instantiation
- `coordinator_trace` contains > 6 entries
- `AgentRunnerError: coordinator_timeout` in integration tests

### Mitigation
1. **Preventive**: TC-1.2 is a sprint-gate test. If Sprint 1/Sprint 2 refactors break it, Sprint 3 doesn't start.
2. **Preventive**: `AgentRunner` enforces a 30-second timeout. Runaway loops die automatically.
3. **Detective**: Integration tests assert `len(result.coordinator_trace) <= 6` as a sanity check.
4. **Architectural**: Document in ADR-012 that specialists MUST have empty `sub_agents` — add a module docstring.

---

## R9 — Sprint 3 blows past 2 days because ADK API differs from docs

**Severity:** High
**Probability:** Medium
**Category:** Schedule

### Narrative
Day 1 Hour 5–6 hits a wall because `llm_request.config.system_instruction.parts[0].text` doesn't exist in the pinned ADK version — it's `llm_request.config.instructions` or the `LlmRequest` has no `.config` attribute at all. The developer spends 4 hours trying variants instead of budgeting 60 minutes. Day 1 ends with no working callback.

### Why it would happen
ADK is on a fast release cadence. The docs at `adk.dev` reflect the main branch, not the pinned version. Sprint 0 pinned `google-adk >= 1.0.0` — any 1.x bump could change the API.

### Early warning signals
- Day 1 Hour 5 imports succeed but `llm_request.config.system_instruction` raises `AttributeError`
- `python -c "from google.adk.models import LlmRequest; help(LlmRequest)"` shows different field names

### Mitigation
1. **Preventive (Day 0 — before the sprint)**: Run the ADK callback example from `[ADK-CB-EX]` verbatim against the pinned version. If it fails, write an ADR documenting the actual API surface BEFORE starting Sprint 3.
2. **Time-boxed (Day 1 Hour 5–6)**: Hard time-box. If the callback API is wrong and fixing it takes > 60 min, switch to the ADR-013 fallback (pre-fetch context in `AgentRunner` and stash in `session.state`).
3. **Detective**: The 8 Open Assumptions in PRD §16 — review at the Day 0 kickoff. Any that fail verification triggers a scope cut.
4. **Escape hatch**: Rollback item #6 (hardcode Priya's context) preserves the NH-48 demo even if the callback is completely broken.

---

## R10 — Prompt rewriting on Day 2 Hour 5 eats the slack buffer

**Severity:** Medium
**Probability:** High
**Category:** Schedule + scope

### Narrative
Day 2 Hour 5 first eval run returns `response_match_score=0.72`. The engineer starts tweaking `coordinator.md`. Each tweak requires a re-run of 10 × 3 = 30 Gemini calls (~90 seconds each). Over 4 iterations that's 6 minutes of waiting per iteration × 10 iterations = 60 minutes JUST on eval runs, plus 60 minutes on prompt editing. The 2-hour slack buffer is gone before Hour 7.

### Why it would happen
Prompt engineering is nonlinear — each tweak can make things worse before better. Without a clear signal, iteration diverges.

### Early warning signals
- Hour 5 first run < 0.75
- Each subsequent run moves < 0.05 in the correct direction
- 3 iterations in, still < 0.80

### Mitigation
1. **Preventive**: Budget Day 2 Hour 5–6 (2 hours) for eval + iteration. If > 3 iterations don't converge, cut to single-case headline test (Rollback item #1).
2. **Constrained iteration**: Per iteration, change ONE thing only. If the score drops, revert. Commit in between.
3. **Use `num_runs=1` during iteration** — 3x faster feedback. Only switch to `num_runs=3` for the final verification.
4. **Detective**: After Hour 6 if score still < 0.8, invoke Rollback item #1.
5. **Lower threshold pragmatically**: If 9 of 10 cases pass at 0.85 and one edge case is at 0.70, document the edge case as a known limitation and proceed.

---

## R11 — Integration tests need Firestore + Gemini + Supermemory stub ALL at once

**Severity:** Medium
**Probability:** Medium
**Category:** Test infrastructure

### Narrative
The `test_nh48_end_to_end` test requires the Firestore emulator running, live Gemini API key set, and the Supermemory stub seeded — three moving pieces. One of them fails (emulator port conflict, Gemini rate limit, seeding script bug). The test intermittently passes depending on which piece is healthy.

### Why it would happen
Complex integration tests have a multiplicative failure probability.

### Early warning signals
- Day 2 Hour 3 test fails with `firestore emulator not available`
- OR `google.api_core.exceptions.ResourceExhausted: 429` from Gemini
- OR `stub_adapter.get_user_context` returns empty dict despite seed

### Mitigation
1. **Preventive**: `tests/integration/conftest.py` has a `firestore_emulator_with_nh48_seed` session-scoped fixture that:
    - Starts the emulator on an unused port (via `firebase emulators:start --only firestore --inspect-functions`)
    - Runs the Sprint 2 seed script
    - Yields, then tears down
2. **Preventive**: Gemini rate-limit backoff — retry with exponential delay on `429` errors in test helpers.
3. **Preventive**: Seed script is idempotent (delete + recreate). Run it at the top of each integration test if needed.
4. **Detective**: Test the fixture in isolation first — `pytest tests/integration/conftest.py -v` before running the actual integration tests.
5. **Corrective**: If emulator keeps flaking, use `mockfirestore` (Sprint 0 dependency) as a fallback for the Firestore side. Sprint 2 already supports this.

---

## R12 — `code-reviewer` skill finds CRITICAL issues on Day 2 Hour 8

**Severity:** Medium
**Probability:** Medium
**Category:** Quality gate

### Narrative
Sprint gate check runs `superpowers:code-reviewer` on the Sprint 3 diff at Hour 8. It finds 3 CRITICAL issues: missing tenant check in a helper function, a log line that includes raw_content, and a hardcoded API key in a test fixture. Fixing them takes 45 minutes. The sprint slips past Apr 17 EOD.

### Why it would happen
Code review at sprint-end is too late. Issues accumulate during rapid iteration.

### Early warning signals
- Day 2 Hour 6 — run a quick lint (`ruff check . && mypy src/`) before starting the docs phase
- Intermediate code reviews on Day 1 Hour 8 commit + Day 2 Hour 4 commit

### Mitigation
1. **Preventive**: Run `code-reviewer` skill on the Day 1 end-of-day commit (Day 1 Hour 8, ~5 min review) AND on Day 2 Hour 4 commit. Catch issues early.
2. **Preventive**: `pre-commit run --all-files` every commit — catches most style + security issues.
3. **Preventive**: `detect-secrets` in pre-commit catches hardcoded keys.
4. **Detective**: Day 2 Hour 8 review is the LAST gate, not the only one.
5. **Corrective**: If critical issues are found at Hour 8, decide: (a) fix within 60 min and slip to Apr 18 AM, OR (b) document as known issues in `review.md` and slip to Sprint 4. User decides.

---

## R13 — The NH-48 eval gold trace drifts from actual Impact output

**Severity:** Medium
**Probability:** Medium
**Category:** Data consistency

### Narrative
PRD §12-J documents a golden trace for NH-48 that includes `impact_weights_used={value_weight:0.35, penalty_weight:0.15, churn_weight:0.50, ...}`. But Sprint 2's Impact Agent produces `{value_weight:0.40, penalty_weight:0.10, churn_weight:0.50}` on a live Gemini call. The integration test asserts exact weights and fails.

### Why it would happen
Dynamic weights are LLM-reasoned — they vary per run. The PRD was written from a sample run, not from Sprint 2's canonical output.

### Early warning signals
- TC-13.1 first run fails on the weight assertion
- Weights vary by > 0.05 across `num_runs=3`

### Mitigation
1. **Preventive**: The integration test asserts `weights_sum == 1.0 ± 0.05` and `len(weights) == 3`, NOT exact values. PRD §12-J is descriptive, not prescriptive.
2. **Preventive**: The headline NH-48 assertions (§2.6) check `critical_path_shipment_id` and `recommended_priority_order` — these ARE deterministic for this input. Weights are qualitative.
3. **Detective**: TC-13.1 failure points directly at the assertion — fix by loosening.
4. **Corrective**: Replace exact-value assertions with range/shape assertions throughout the golden trace.

---

## R14 — ADR-012 / ADR-013 get written at Hour 8 as an afterthought

**Severity:** Low
**Probability:** High
**Category:** Documentation debt

### Narrative
The ADRs are on the Day 2 Hour 8 checklist but get rushed because the sprint is behind schedule. They end up as 30-line stubs that don't actually document the decision or alternatives considered.

### Why it would happen
Documentation always slips when code work runs late.

### Early warning signals
- Day 2 Hour 7 — ADR files don't exist yet
- Day 2 Hour 8 ADR word count < 300

### Mitigation
1. **Preventive**: Write ADR-012 and ADR-013 on Day 1 Hour 6 (right after the callback middleware lands) — while the context is fresh. The decision is made; just record it.
2. **Preventive**: Use the `docs/templates/adr-template.md` to enforce minimum sections.
3. **Detective**: Sprint gate check (`wc -l` per doc ≥ 30) catches stubs.
4. **Corrective**: If ADRs are stubs at Hour 8, flag in `review.md` as a known gap and budget 30 min on Sprint 4 Day 1 to fill them in.

---

## R15 — Supermemory SDK API drift breaks `client.search.execute`

**Severity:** Low
**Probability:** Low
**Category:** External dependency

### Narrative
The Supermemory Python SDK changes its `search` API between the version Sprint 2 integrated against and Sprint 3's usage. `client.search.execute(...)` becomes `client.memories.search(...)`. Every adapter method fails at runtime.

### Why it would happen
Third-party SDK minor version bumps sometimes include breaking changes.

### Early warning signals
- Day 1 Hour 3 — `test_get_recent_history_happy` fails with `AttributeError: 'Supermemory' object has no attribute 'search'`

### Mitigation
1. **Preventive**: Pin the Supermemory SDK version in `pyproject.toml`. Sprint 2 established the pin.
2. **Graceful fallback**: `build_with_fallback()` catches any `AttributeError` on `client.search.execute` → returns stub.
3. **Detective**: TC-11.* unit tests mock the SDK, so they don't catch real API drift. Add ONE real-call smoke test that hits the live SDK — marked `@pytest.mark.slow` so it doesn't run in CI.
4. **Corrective**: Update the adapter's method calls to match the new API surface. 15-minute fix.

---

## Summary Matrix

| # | Risk | Prob | Impact | Mitigation | Detection Hour |
|---|------|------|--------|-----------|----------------|
| R1 | AutoFlow description similarity | Medium | High | Distinctness test + manual smoke | Day 2 H1 |
| R2 | Callback blocks event loop | High | Medium | `_run_async` bridge + ADR-013 fallback | Day 1 H8 |
| R3 | Rule B LLM bypass | Medium | Critical | Upstream safety check in AgentRunner | Day 2 H3 |
| R4 | Cross-tenant Supermemory leak | Medium | Critical | `_namespace` helper + TC-13.2 | Day 2 H7 |
| R5 | Eval response_match stuck at 0.6 | Medium | High | Iterate prompts + cut threshold | Day 2 H5–6 |
| R6 | Unicode sanitization edge case | Low | High | NFKC normalize + adversarial fuzz | Day 2 H7 |
| R7 | Sub-agent crash cascade | Medium | Medium | `try/except` in AgentRunner | Day 2 H4 |
| R8 | Infinite delegation loop | Low | High | Specialists have `sub_agents=[]` + 30s timeout | Day 1 H2 |
| R9 | ADK API doesn't match docs | Medium | High | Day 0 verification + ADR-013 fallback | Day 1 H5 |
| R10 | Prompt iteration eats slack | High | Medium | Time-box + Rollback #1 | Day 2 H6 |
| R11 | Integration test flakiness | Medium | Medium | Idempotent fixtures + emulator isolation | Day 2 H3 |
| R12 | `code-reviewer` finds criticals | Medium | Medium | Mid-sprint reviews on Day 1 H8 + Day 2 H4 | Day 2 H8 |
| R13 | Golden trace weight drift | Medium | Medium | Range assertions instead of exact | Day 2 H3 |
| R14 | ADR documentation debt | High | Low | Write ADRs on Day 1 H6 | Day 2 H7 |
| R15 | Supermemory SDK drift | Low | Low | Pin version + graceful fallback | Day 1 H3 |

**Top 5 to watch (by severity × probability):**
1. **R2** — callback event loop (High × Medium) — Day 1 Hour 5–6 is the critical window
2. **R3** — Rule B bypass (Medium × Critical) — mitigated architecturally, monitor test results
3. **R4** — cross-tenant leak (Medium × Critical) — TC-13.2 is the gate
4. **R5** — eval threshold stuck (Medium × High) — Day 2 afternoon risk
5. **R9** — ADK API drift (Medium × High) — Day 0 verification step

---

## Kill-switch Triggers (when to invoke rollback)

Per PRD §13, if ANY of these fire, execute the corresponding rollback item:

| Trigger | Rollback Item | Saves |
|---------|---------------|-------|
| Day 1 Hour 6 — callback middleware still doesn't work | ADR-013 fallback: pre-fetch in AgentRunner | 90 min |
| Day 1 EOD — `adk web` smoke fails | Rollback #5: cut Rules A + D | 60 min |
| Day 2 Hour 6 — eval < 0.75 after 3 iterations | Rollback #1: cut ADK eval harness | 90 min |
| Day 2 Hour 7 — cross-tenant leak found | BLOCK sprint; do not close until fixed | — |
| Day 2 Hour 8 — `code-reviewer` CRITICAL findings | Fix or document + slip to Sprint 4 Day 1 AM | variable |

---

## Cross-References

- PRD: `./prd.md` §10 (summary), §13 (rollback plan), §16 (open assumptions)
- Test Plan: `./test-plan.md` (detection tests for each risk)
- Spec: [[Supply-Chain-Agent-Spec-Coordinator]] (authoritative delegation rules)
- Prior sprints: `./../sprint-0/risks.md`, `./../sprint-1/risks.md`, `./../sprint-2/risks.md`

---

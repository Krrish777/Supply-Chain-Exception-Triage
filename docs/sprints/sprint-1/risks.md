---
title: "Sprint 1 Risks — Pre-mortem for Classifier Agent"
type: deep-dive
domains: [supply-chain, hackathon, sdlc, risk-management]
last_updated: 2026-04-10
status: active
confidence: high
sources: ["./prd.md", "[[Supply-Chain-Agent-Spec-Classifier]]", "[[Supply-Chain-Research-Sources]]"]
---

# Sprint 1 Pre-Mortem — Classifier Agent

> **Pre-mortem framing (Gary Klein):** Imagine it's Apr 14, 2026 — Sprint 1 was supposed to finish Apr 13 — and the Classifier is late, broken, or a stability drag on Sprint 2. Walk the failure backwards. What went wrong?

---

## 1. Top 12 Failure Modes (Ranked by Expected Loss)

Expected loss = Probability × Impact-hours. Mitigation cost is separate.

| # | Failure mode | Prob | Impact (hrs lost) | Expected loss | Mitigation cost | Mitigate in PRD? |
|---|---|---|---|---|---|---|
| 1 | Few-shot prompt doesn't generalize — F1 stuck at 0.70-0.78 | 0.45 | 8 | 3.6 | Medium | ✅ |
| 2 | Hinglish code-switch confuses Gemini mid-sentence | 0.35 | 6 | 2.1 | Low | ✅ |
| 3 | ADK `AgentEvaluator` API surface differs from docs (SDK drift) | 0.35 | 5 | 1.75 | Medium | ✅ |
| 4 | Tool docstrings insufficient — LLM never calls `check_safety_keywords` first | 0.30 | 5 | 1.5 | Low | ✅ |
| 5 | Safety keyword list has false negatives (real safety missed) | 0.30 | 5 | 1.5 | Low | ✅ |
| 6 | Guardrails AI + Gemini integration breaks on Pydantic v2 enum | 0.25 | 6 | 1.5 | Medium | ✅ |
| 7 | Firestore emulator seed data drifts from schema | 0.25 | 4 | 1.0 | Low | ✅ |
| 8 | Sprint 0 dependency not actually green (schemas wrong) | 0.20 | 5 | 1.0 | Medium | ✅ |
| 9 | Gemini rate-limit during Day 2 eval runs | 0.30 | 3 | 0.9 | Low | ✅ |
| 10 | Validator false positive — Rule 3 escalates benign small-shipment cases | 0.25 | 3 | 0.75 | Low | ✅ |
| 11 | Prompt file bloats past 10 KB (slow + expensive every call) | 0.15 | 2 | 0.3 | Low | ✅ |
| 12 | Flaky tests from LLM nondeterminism in `AgentEvaluator` | 0.30 | 2 | 0.6 | Low | ✅ |

**Sum of expected loss ≈ 16 hours.** Sprint 1 has 18 hours budget (16 + 2 slack). Without mitigation, Sprint 1 is 90% likely to overrun. **With the mitigations below, expected loss drops to ~5 hours** (risks 1, 2, 5 are the dominant residual).

---

## 2. Failure Walk-Backs (Detailed)

### Risk 1 — Few-shot prompt doesn't generalize

**Symptoms:** F1 stuck at 0.70–0.78. Eval cases fail on edge types (`festival_demand_spike`, `documentation_missing`, `driver_unavailable`). NH-48 works; everything else is shaky.

**Root causes:**
- Only 3 few-shot examples, all clustered in 3 of 6 taxonomy types (carrier / customer / safety)
- Format inconsistency across examples (subtle indentation / JSON spacing drift)
- LLM fixates on the 3 examples as the total space of classifications
- `response_mime_type: application/json` + `response_schema` not used — JSON is requested by prompt, not by API

**Mitigations (in PRD §12 Snippet B + §12 Snippet J):**
- Fixture test (Snippet J) enforces byte-identical structural formatting across examples
- Prompt explicitly instructs "You MUST pick ONE of the predefined `<taxonomy>` types and subtypes"
- ADK `output_schema=ClassificationResult` drives Gemini to structured output (not prompt-based JSON)
- 12-case eval dataset covers all 6 types (≥ 2 per type) — drives iteration during Day 2 Hour 5-6
- Rollback plan §13 cuts eval from 12 → 10 if we need iteration headroom

**Residual risk:** MEDIUM. If F1 stalls at 0.78, use rollback option 1 (cut eval cases) and document the gap in `retro.md`.

---

### Risk 2 — Hinglish code-switch confuses Gemini mid-sentence

**Symptoms:** Hinglish eval cases (#1 NH-48, #5 e-way bill, #8 damage claim) classify correctly about half the time. Gemini returns English sentences but with wrong subtypes, or misreads `ghayal` as a regular word.

**Root causes (Hinglish multilingual AI — open sourcing item, partially covered by Research Sources Topic 2 / Prompt Engineering):**
- Gemini Hindi satisfaction is 53% in judge tasks — below English
- Code-switching mid-sentence is a 2026 frontier problem
- Small training data on Indian 3PL vocabulary (`eway bill`, `chalan`, `transporter`)
- Judge-side instructions are in English while content is in Hinglish

**Mitigations:**
- `check_safety_keywords` runs a deterministic Hinglish phrase scan BEFORE the LLM classifies (belt + braces)
- Prompt instructs to call `translate_text` when `original_language != "en"` — English is then the classification language
- Eval dataset has 3 Hinglish cases (diverse contexts: vehicle breakdown, border hold, damage complaint) so we can iterate on real failures
- `check_safety_keywords` keyword list includes both Devanagari AND romanized forms of Hindi safety words

**Residual risk:** MEDIUM. Acceptable to ship Sprint 1 with Hinglish F1 = 0.80 as long as English F1 = 0.90 and safety precision = 0.95. Track in `retro.md` as a Tier 2 research item.

---

### Risk 3 — ADK `AgentEvaluator` API drift (`filter_tags` unverified)

**Symptoms:** `AgentEvaluator.evaluate()` signature doesn't match the FutureAGI guide / ADK docs. Tests fail with `TypeError: unexpected keyword argument 'filter_tags'`. Eval dataset JSON format is rejected. The `filter_tags` kwarg used in Snippet I to isolate the safety subset may not exist in the installed `google-adk` version.

**Root causes:**
- Google ADK is a 2025-2026 SDK with frequent breaking changes between minor versions
- FutureAGI guide, ADK docs, and the installed package version can all describe different API surfaces
- `filter_tags` is convenient but unverified — may need dataset partitioning instead

**Mitigations:**
- Pin `google-adk` version in `pyproject.toml` during Sprint 0.
- **Day 1 Hour 1 `filter_tags` smoke test** (NEW): `tests/unit/integrations/test_adk_api_surface.py::test_agent_evaluator_supports_filter_tags` runs `inspect.signature(AgentEvaluator.evaluate)` and asserts `filter_tags` is a parameter. This fires before any business logic is written. If it fails, apply the rollback below immediately.
- Also smoke-import `from google.adk.evaluation import AgentEvaluator` on Day 1 Hour 1 to catch the case where the module path itself moved.
- **Documented fallback** (PRD §13 Rollback option 6): if `filter_tags` is unavailable, split `classifier_eval.json` into `classifier_eval_main.json` (10 non-safety cases → F1 ≥ 0.85 assertion) and `classifier_eval_safety.json` (3 safety cases → 100% case-by-case pass). Both tests then pass the relevant file path to `AgentEvaluator.evaluate()` without any `filter_tags` kwarg. Refactor cost ~15 min.
- The Sprint 1 PRD §16 assumption #12 flags this openly so the reviewer knows it is an unverified API call.

**Residual risk:** LOW. The Hour-1 smoke test catches API drift before any downstream code depends on it, and the fallback is a straightforward file split.

---

### Risk 4 — Tool docstrings insufficient, LLM skips safety scan

**Symptoms:** Classifier occasionally emits a classification without calling `check_safety_keywords`. The Sunil-Verma accident case slips past because the LLM thinks it has enough context from the raw text alone.

**Root causes (from Research Sources Topic 1 — Google ADK, specifically the ADK Function Tools docs):**
- ADK function tools are dispatched based entirely on the docstring — if the docstring doesn't say "MUST be called first," the LLM has discretion
- Gemini 2.5 Flash optimizes for token efficiency and will skip tools it deems redundant

**Mitigations:**
- Tool docstring in Snippet D opens with "This tool MUST be called first by the Classifier (see workflow step 1)."
- Prompt workflow step 1 is written in `<workflow>` XML tags with imperative voice: "ALWAYS call `check_safety_keywords(raw_content)` FIRST."
- Test 7.10 asserts tool-call order via a spy — if the order is wrong, the test fails.
- Integration test asserts `tools_used` includes `check_safety_keywords` for every eval case.

**Residual risk:** LOW. The spy test catches regressions immediately.

---

### Risk 5 — Safety keyword list has false negatives

**Symptoms:** A real driver injury comes in as "Ramesh gir gaya, uski haalat kharab hai, jaldi ambulance bhej do" and `check_safety_keywords` misses it because the list doesn't have `gir gaya` or `haalat kharab`.

**Root causes:**
- The keyword list in the Classifier spec is a starter set, not exhaustive
- Small Indian 3PL vocabulary uses colloquial Hinglish we haven't captured
- The regex patterns are anchored on exact phrases, not semantic meaning

**Mitigations:**
- `ambulance` is in the English keyword list — this case would catch on "ambulance" alone
- LLM is the SECOND line of defense — even if the keyword scan misses, the LLM can still classify as `safety_incident` because the `<severity_heuristics>` block instructs CRITICAL on "Safety involved"
- The validator's Rule 1 then forces CRITICAL severity regardless of whether the keyword scan caught it
- `retro.md` item: expand keyword list after Sprint 1 with new cases found during NH-48 demo rehearsal

**Residual risk:** MEDIUM. Ongoing concern. Tracked for Tier 2 as "build Hinglish safety corpus from real dispatch messages."

---

### Risk 6 — Guardrails AI + Gemini + Pydantic v2 enum

**Symptoms:** `Guard.for_pydantic(ClassificationResult)` fails to parse Gemini output because Pydantic v2 handles enum serialization differently from v1, and Guardrails' validator was written for v1.

**Root causes:**
- Guardrails AI has had historical Pydantic v1 → v2 migration pain
- Gemini's structured output sometimes emits enum fields as strings with different case ("critical" vs "CRITICAL")

**Mitigations:**
- `Severity` enum values in `schemas/classification.py` are UPPERCASE strings
- The prompt's output format section explicitly says "confidence must be a float in [0.0, 1.0]" and enum values are shown in examples
- Sprint 0 `Guard.for_pydantic(SomeModel)` smoke test is in the dependency checklist — if Guardrails + Pydantic v2 is broken, it's caught in Sprint 0
- Rollback option 3: drop Guardrails wrapper entirely for Sprint 1, rely on ADK `output_schema` alone, defer Guard to Sprint 2

**Residual risk:** LOW. Rollback is cheap.

---

### Risk 7 — Firestore emulator seed data drifts from schema

**Symptoms:** `get_festival_context` returns an empty list every time because the seed JSON has `festival_date` but the query filters on `date`.

**Root causes:**
- Sprint 0 may have created the collection with a different field name than Sprint 1 expects
- `scripts/seed_firestore.py` is not type-checked against the Firestore schema docs

**Mitigations:**
- Snippet E uses `date` field name matching `Supply-Chain-Firestore-Schema-Tier1.md` §Collection 6 exactly
- Tests 4.1–4.6 run against the real emulator, so schema drift fails the test immediately
- Day 1 Hour 4-5 explicitly creates or verifies the seed JSON before tests run

**Residual risk:** LOW.

---

### Risk 8 — Sprint 0 gate not actually green

**Symptoms:** Sprint 1 engineer starts Day 1, tries to `from supply_chain_triage.schemas.classification import ClassificationResult`, and gets an ImportError. Sprint 0 marked complete but forgot to actually write `classification.py`.

**Root causes:**
- Over-ambitious Sprint 0 scope, some items checked off without evidence
- CI green doesn't imply "all acceptance criteria met" — it implies "tests we wrote pass"

**Mitigations:**
- Sprint 1 PRD §7 has an explicit 13-item dependency checklist with boxes to tick BEFORE starting Sprint 1
- Day 1 Hour 1 is "instantiate the agent, write the instantiation test" — this catches missing schema immediately
- User-reviewer verifies Sprint 0 gate before authorizing Sprint 1 kickoff

**Residual risk:** LOW. The checklist is the safety.

---

### Risk 9 — Gemini rate-limit during Day 2 eval runs

**Symptoms:** Day 2 Hour 5-6 runs `AgentEvaluator.evaluate()` 5 times to iterate on prompts; Gemini API returns 429 Too Many Requests and eval blocks for 60 seconds each time.

**Root causes:**
- Free-tier Gemini quota is ~15 req/min; each eval run = 12 LLM calls (one per case)
- Running eval twice in the same minute hits the limit

**Mitigations:**
- Eval is run sequentially, not in parallel
- Sprint 0 provisioned a paid Gemini API key OR the free quota is enough for ~3 eval runs/minute
- `translate_text` has exponential backoff on 429 (Snippet C)
- If quota is exhausted, use `@pytest.mark.integration` gating — only run the full eval on push, not on every save

**Residual risk:** LOW–MEDIUM. Worst case: 30 minutes of waiting during Day 2 Hour 5-6. Budget absorbs it.

---

### Risk 10 — Validator Rule 3 false positive for small companies

**Symptoms:** A small 3PL with ₹5L daily revenue has a ₹30k shipment at risk. Rule 3 fires (30k > 0.05 × 5L = 25k) and escalates to HIGH. The LLM correctly classified it MEDIUM. User perceives false positive.

**Root causes:**
- 5% is a guess from the Classifier spec, not validated against real 3PLs
- Small companies have much higher variance in daily revenue

**Mitigations:**
- Rule 3 requires BOTH `value_at_risk_inr > 0` AND `company_avg_daily_revenue_inr > 0` — missing fields skip the rule
- Test 6.6 confirms skip-on-missing
- If it's a problem in practice, bump the threshold from 5% → 10% in a post-Sprint-1 tweak (one-line change)
- `retro.md` records Rule 3 hit rate from eval runs so we can tune

**Residual risk:** LOW for Sprint 1 (eval has 1 case that triggers Rule 3). Medium for post-hackathon.

---

### Risk 11 — Prompt file bloats past 10 KB

**Symptoms:** During Day 1 Hour 6-7, the 3 few-shot examples plus taxonomy plus heuristics grow to 14 KB. Every Classifier call pays the extra tokens.

**Root causes:**
- JSON examples are verbose
- Writer (me) over-documents in prompt

**Mitigations:**
- Fixture test `test_prompt_file_size_under_10kb` (Snippet J) fails fast
- If the test fails, compress by:
  - Stripping tool_calls block from examples (keep only input + expected_output)
  - Cutting Example 2 (keep only NH-48 + safety)

**Residual risk:** LOW.

---

### Risk 12 — Flaky tests from LLM nondeterminism

**Symptoms:** `test_classifier_eval_f1_at_least_85` passes on Day 2 Hour 5 but fails on Day 2 Hour 8 with no code change. F1 is 0.87 one run and 0.82 the next.

**Root causes:**
- `temperature=0` is deterministic in theory but Gemini has subtle nondeterminism in its safety filter path
- `final_response_match_v2` is a rubric-based metric with paraphrase tolerance — occasionally an edge case flips

**Mitigations:**
- `temperature=0` is set on all Gemini calls (enforced in Snippet C and classifier prompt)
- Eval uses rubric-based criteria (not exact-match) so paraphrases don't flip results
- `final_response_match_v2` threshold per case is set to 0.75-0.90 (intentional slack)
- If a single case is flaky, drop its threshold to 0.75 or tag it `@pytest.mark.xfail_on_retry` with a note
- Rolling-average assertion: `assert f1 >= 0.85` allows one flaky case below target as long as overall F1 holds

**Residual risk:** MEDIUM. Track test flakiness in `test-report.md`; if > 2 flakes, add retry logic or cut flaky cases.

---

## 3. Cross-Sprint Risks (Not mitigated in Sprint 1)

These risks affect Sprint 1 indirectly via Sprint 0 quality:

| Cross-sprint risk | Owned by | Sprint 1 impact |
|-------------------|----------|-----------------|
| Sprint 0 Firestore emulator is unreliable on Windows | Sprint 0 | Tool tests 4.x and 5.x can't run → defer to integration-only |
| Sprint 0 `Guard.for_pydantic` smoke test was skipped | Sprint 0 | Sprint 1 discovers the Pydantic v2 bug (Risk 6) |
| Sprint 0 did not seed a minimal dev company profile | Sprint 0 | Rule 3 test 6.4 can't run without a `company_context` fixture |

**Mitigation:** PRD §7 dependency checklist has explicit items for all three. Day 1 Hour 1 stops if any is missing.

---

## 4. Unknown Unknowns Budget

The 2-hour slack buffer in the 18-hour Sprint 1 budget is explicitly reserved for unknown unknowns. If no known risks fire, the slack goes to expanding the eval dataset from 12 → 18 cases (which strengthens the F1 number for the hackathon pitch).

---

## 5. Pre-Mortem Actions (Concrete)

Before Day 1 starts:

1. **Run Sprint 0 dependency checklist** (PRD §7) and tick all boxes; acknowledge the §7.1 backfill list (`get_secret`, `get_firestore_client`, `audit_event`, import rename sweep) that gets done in Sprint 1 Hour 1
2. **Smoke import** `from google.adk.evaluation import AgentEvaluator` to catch ADK module-path drift
3. **`filter_tags` signature smoke test** — `inspect.signature(AgentEvaluator.evaluate)` must include `filter_tags`; if not, apply PRD §13 Rollback option 6 (split eval dataset) immediately before writing downstream code
4. **Smoke call** `Guard.for_pydantic(ClassificationResult)` to catch Guardrails + Pydantic v2 bug
5. **Verify Firestore emulator** runs and `festival_calendar` + `monsoon_regions` collections exist (even if empty)
6. **Confirm Gemini API key** is provisioned and has > 15 RPM quota (or paid tier)
7. **Print** PRD §8 Day-by-Day schedule on paper (metaphorically) so the engineer can't drift

---

## 6. Post-Sprint-1 Retro Prompts (for `retro.md`)

These are the questions I'd want answered after Sprint 1:

- Did the fixture test (Snippet J) actually prevent format drift, or was it window-dressing?
- How many iterations did Day 2 Hour 5-6 take to hit F1 ≥ 0.85? (target: ≤ 3)
- Which tool did the LLM skip most often, and did the docstring fix work?
- Did Rule 3 fire on any benign case? If yes, should we bump to 10%?
- Was the prompt-injection defense tested in production-like conditions, or only the one eval case?
- Did Gemini rate-limit bite us? If yes, how much time lost?
- Would we recommend dropping Guardrails entirely if starting over?

---

## 7. Cross-References

- `./prd.md` — Sprint 1 PRD (scope, AC, code snippets, rollback plan §13)
- `./test-plan.md` — test-level Given/When/Then
- [[Supply-Chain-Agent-Spec-Classifier]] — taxonomy + severity matrix source
- [[Supply-Chain-Sprint-Plan-Spiral-SDLC]] — Spiral SDLC phase definitions
- [[Supply-Chain-Research-Sources]] — Topic 1 (Google ADK; covers ADK tool design + AgentEvaluator), Topic 2 (Prompt Engineering; partial Hinglish coverage), Topic 3 (Prompt Format Research), Topic 5 (LLM Guardrails). Open sourcing items for few-shot format, Hinglish multilingual, and F1-for-imbalanced are flagged in PRD §15 and §16.

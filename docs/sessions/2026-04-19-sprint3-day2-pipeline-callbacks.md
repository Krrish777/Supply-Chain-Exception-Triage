---
title: "Sprint 3 Day 2 — Pipeline Callbacks"
date: 2026-04-19
sprint: 3
day: 2
status: complete
commit: c9f0805
---

# Sprint 3 Day 2 — Pipeline Callbacks

## What was done this session

### 1. Research + planning (full SDLC research phase)
- Read all Sprint 3 docs: `docs/sprints/sprint-3/prd.md`, `impl-log.md`, `next-sprint-handoff-v2.md`
- Read `docs/research/coordinator-orchestration-patterns.md` (sections 1-7, ADK callback mechanics, Rule B/C/F specs)
- Fetched live ADK docs to confirm `before_agent_callback` state-mutation semantics and SequentialAgent short-circuit behaviour
- Ran 5 clarifying questions with the user → 4 key design decisions locked in (see below)
- Wrote and got approval for a Day 2 PRD/plan

### 2. Design decisions made this session

| Decision | Chosen | Why |
|---|---|---|
| `pipeline/` location | `modules/triage/pipeline/` (module-level subpackage) | Sits between agents/ and runners/ in architecture; Day 3 adds factory |
| Rule B attachment point | Pipeline-level `before_agent_callback` | Returning Content at pipeline level skips ENTIRE SequentialAgent — no two-sentinel needed |
| Keyword source | Separate from classifier | Rule B (pre-LLM) vs classifier (post-LLM) — different purposes, no import coupling |
| Test path | `tests/unit/modules/triage/pipeline/` | 1:1 mirror of src/ per testing rules |

### 3. Infrastructure changes (needed before writing code)
- **`.claude/hooks/check_placement.py`** — added `modules/*/pipeline/**/*.py` to allowlist
- **`.claude/rules/placement.md`** — added pipeline/ row to placement table
- **`pyproject.toml`** — two additions:
  - `src/**pipeline/**` → TID251 per-file-ignore (pipeline/ is ADK orchestration tier, legitimately imports `google.adk.*` types)
  - `tests/**` → added RUF001 + RUF003 (tests intentionally use full-width Unicode for NFKC normalization test data)

### 4. New files created

#### `src/supply_chain_triage/modules/triage/pipeline/__init__.py`
Empty package marker. Day 3 will add `create_triage_pipeline()` factory here.

#### `src/supply_chain_triage/modules/triage/pipeline/_constants.py`
- `_RULE_B_SAFETY_KEYWORDS_EN` — 16 English safety terms (frozenset)
- `_RULE_B_SAFETY_KEYWORDS_HI` — 10 Hindi-transliterated / Hinglish terms (frozenset)
- `_RULE_B_SAFETY_KEYWORDS` — union of both (the actual lookup set)
- `_SAFETY_PLACEHOLDER_BASE` — minimal valid `ClassificationResult`-shaped dict written to `triage:classification` when Rule B fires (prevents KeyError in runner assembly, which always reads this key)

#### `src/supply_chain_triage/modules/triage/pipeline/callbacks.py`
Two public callbacks + private helpers:

**`_rule_b_safety_check(callback_context)`**
- Attached to `triage_pipeline` SequentialAgent's `before_agent_callback` (Day 3 wire-up)
- Reads `triage:event_raw_text` from state; returns None if absent (graceful proceed)
- NFKC + casefold normalisation, then substring match vs `_RULE_B_SAFETY_KEYWORDS`
- On match: writes 6 state keys (`triage:status`, `triage:skip_impact`, `triage:safety_match`, `triage:escalation_priority`, `triage:rule_b_applied`, `triage:classification` placeholder), returns `Content(role="model", ...)`
- On no match: returns None

**`_rule_cf_skip_check(callback_context)`**
- Attached to `impact` sub-agent's `before_agent_callback` (Day 3 wire-up)
- Priority: B-sentinel > C (regulatory force-run) > F (LOW skip)
- Rule B sentinel: `triage:skip_impact=True` → return skip Content (defensive guard)
- Rule C: `exception_type == "regulatory_compliance"` → return None (force run Impact), sets `triage:rule_c_applied=True`
- Rule F: `severity == "LOW"` → return skip Content, sets `triage:skip_impact=True`, `triage:status="complete"`, `triage:rule_f_applied=True`

Private helpers: `_skip_content()`, `_classification_dict()`, `_classification_regulatory()`, `_classification_severity()`, `_write_safety_placeholder()`

#### `tests/unit/modules/triage/pipeline/test_callbacks.py`
10 unit tests (U-1…U-10), all pass:

| Test | Rule | Verifies |
|---|---|---|
| U-1 `test_no_event_text_proceeds` | B | Absent key → None |
| U-2 `test_empty_string_proceeds` | B | Empty string → None |
| U-3 `test_english_keyword_returns_content` | B | "fire" → Content + 4 state keys |
| U-4 `test_hindi_keyword_returns_content` | B | "khatarnak" → Content |
| U-5 `test_nfkc_normalization_catches_fullwidth` | B | Full-width ｆｉｒｅ → normalised + matched |
| U-6 `test_safety_match_list_populated` | B | matched list has all hit keywords |
| U-7 `test_placeholder_classification_written` | B | placeholder JSON valid (safety_incident, CRITICAL) |
| U-8 `test_rule_b_sentinel_skips_impact` | C/F | skip_impact pre-set → Content |
| U-9 `test_regulatory_forces_impact` | C | regulatory_compliance → None + rule_c_applied |
| U-10 `test_low_severity_skips_impact` | F | LOW + no sentinel → Content + status=complete |

### 5. Verification results
- `uv run pytest tests/unit/` → **199 passed, 1 skipped** (live Gemini test, expected)
- `uv run ruff check src/supply_chain_triage/modules/triage/pipeline/` → clean
- `uv run mypy src/supply_chain_triage/modules/triage/pipeline/` → clean
- `uv run lint-imports` → 5 contracts kept, 0 broken
- All pre-commit hooks passed on commit

### 6. Commit
```
c9f0805  feat(pipeline): add Rule B + Rule C/F callbacks with safety keyword list
```

---

## Day 3 handoff — what to do next

**Day 3 deliverables (Apr 21):**

1. **`modules/triage/pipeline/__init__.py`** — implement `create_triage_pipeline()` factory:
   ```python
   from google.adk.agents import SequentialAgent
   from supply_chain_triage.modules.triage.agents.classifier.agent import create_classifier
   from supply_chain_triage.modules.triage.agents.impact.agent import create_impact
   from supply_chain_triage.modules.triage.pipeline.callbacks import (
       _rule_b_safety_check, _rule_cf_skip_check
   )

   def create_triage_pipeline() -> SequentialAgent:
       classifier = create_classifier()
       impact = create_impact(before_agent_callback=_rule_cf_skip_check)
       return SequentialAgent(
           name="triage_pipeline",
           before_agent_callback=_rule_b_safety_check,
           sub_agents=[classifier, impact],
       )
   ```

2. **`create_impact()` needs a `before_agent_callback` parameter** — modify `modules/triage/agents/impact/agent.py` to accept it (currently hardcoded, needs to be injectable for the pipeline wire-up).

3. **`runners/triage_runner.py`** — blocking path that:
   - Seeds `triage:event_id` and `triage:event_raw_text` into state before dispatching
   - Calls `Runner.run_async(create_triage_pipeline(), ...)`
   - Assembles `TriageResult` from state keys after run

4. **Tests:** `tests/unit/triage/test_pipeline_factory.py` (U-11…U-13), `tests/unit/runners/test_triage_runner.py` (U-14…U-18 blocking path)

5. **Integration test:** `tests/integration/test_triage_pipeline.py` (I-1 NH-48 full run against emulator)

**State keys the runner must seed before dispatch:**
- `triage:event_id` — the exception event ID
- `triage:event_raw_text` — raw text of the event (for Rule B keyword scan)

**State keys the runner reads for assembly:**
- `triage:classification` — JSON string → `ClassificationResult`
- `triage:impact` — JSON string → `ImpactResult` (may be absent if Rule B or F fired)
- `triage:status` — `"complete" | "partial" | "escalated_to_human_safety" | "escalated_to_human"`
- `triage:skip_impact`, `triage:rule_b_applied`, `triage:rule_c_applied`, `triage:rule_f_applied` — audit flags
- `triage:safety_match` — matched keywords (for audit + UI display)
- `triage:escalation_priority` — `"safety" | "standard" | ...`

---

## Open questions (carry to Day 3)
- `create_impact()` parameter injection: accept `before_agent_callback` as a factory arg, or wire it differently?
- Runner: should `triage:event_raw_text` be seeded from Firestore (fetched by runner before dispatch) or passed in directly by the API route? Decision affects runner interface.

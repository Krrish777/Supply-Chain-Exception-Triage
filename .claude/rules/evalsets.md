---
description: ADK evalset authoring — schema, scenario coverage, rubric authoring, trajectory modes, versioning, CI tiering
paths: ["evals/**"]
---

# Evalset rules

Evalsets validate agent behavior. They're **not** pytests (which validate code) — see `.claude/rules/testing.md` for the split. Every leaf agent ships with an evalset from its first merge.

## 1. Current schema (post-Pydantic migration)

```
EvalSet
  eval_cases: list[EvalCase]
    EvalCase
      eval_id: str
      conversation: list[Invocation]
        Invocation
          invocation_id: str
          user_content: Content
          final_response: Content
          intermediate_data:
            tool_uses: list[ToolCall]             # NOT "expected_tool_use"
            intermediate_responses: list[Content] # NOT "expected_intermediate_agent_responses"
      session_input:
        app_name: str                             # MUST match the agent directory name
        user_id: str
        state: dict
```

Legacy field names (`expected_tool_use`, `expected_intermediate_agent_responses`, `reference`) are **pre-Pydantic**. If you encounter them, migrate via `AgentEvaluator.migrate_eval_data_to_new_schema`.

## 2. Coverage target per leaf agent (15-25 cases)

| Scenario type | Count | Rationale |
|---|---|---|
| Happy path | ~10 (one per category × EN/HI/Hinglish) | Gate F1 / trajectory match |
| Edge case | 5 | Ambiguous boundary, missing fields, confusable classes |
| Safety | 3-5 | 100% pass required; escalation invariants |
| Adversarial / prompt injection | 2-3 | User text attempts to inject instructions via `<user_context>` |
| Degraded tool | 2 | Tool returns `{"status":"retry"}` or `{"status":"error"}` — agent handles |
| Missing state | 1 | Upstream agent output absent — graceful degradation per `agents.md` §12 |

**Never happy-path-only.** `adk-samples` evalsets cluster 10-20 cases; we shoot for the upper end because our domain has high consequence (driver safety escalation).

## 3. Rubric authoring (for `rubric_based_final_response_quality_v1`)

- **One assertion per rubric.** Never compound ("response is polite AND references shipment ID AND …").
- **Binary yes/no.** Never 1-5 numeric scales — LLM judges are inconsistent on graded scoring.
- **Human-consistency test** — two people should agree on the yes/no answer for every case. If they don't, the rubric is too vague.
- **`num_samples: 5`** majority vote to reduce judge flakiness; use `num_samples: 9` for safety rubrics.

Bad: *"Response is professional."* (subjective, graded)
Good: *"Response does not contain profanity or slurs."* (binary, verifiable)

Bad: *"The classification matches the input."* (vague)
Good: *"The classification `category` field equals `carrier_strike` when the input mentions bandh, hartal, strike, or labor action."*

## 4. Trajectory scoring — `tool_trajectory_avg_score`

Three modes:

| Mode | Behavior |
|---|---|
| `EXACT` (default) | Tool calls must match list exactly, in order |
| `IN_ORDER` | Expected calls must appear in order; extra calls allowed |
| `ANY_ORDER` | Expected calls must appear; order irrelevant (use for `ParallelAgent`) |

- **All-or-nothing per invocation** — no partial credit within a turn. Averaging across turns produces the graded score.
- **Apply trajectory scoring to deterministic leaf agents** (e.g. fetcher in a fetcher+formatter pipeline).
- **Never apply trajectory scoring to the Coordinator** — ADK bug adk-python#3434 makes `transfer_to_agent` IDs non-deterministic. Use rubric-based evaluation on Coordinator instead.
- For graded reasoning quality (not trajectory), use `rubric_based_tool_use_quality_v1`.

## 5. Classification metrics (computed outside ADK)

ADK doesn't compute multi-class F1 natively. Parse the structured `category` field from each `final_response` and compute F1 with scikit-learn in a pytest that ingests the evalset results:

```python
from sklearn.metrics import f1_score, classification_report
# aggregate over evalset runs
```

### Realistic Gemini 2.5 Flash multilingual targets

| Language | F1 expectation (no fine-tune) |
|---|---|
| English | ~0.85 |
| Hindi | 0.78 – 0.85 |
| Hinglish | 0.70 – 0.80 |

**To hit Sprint 1's aggregate 0.85:** weight the evalset toward EN/HI, add a Hinglish few-shot to the prompt (see `.claude/rules/prompts.md` §7), and accept that Hinglish will drag the aggregate toward ~0.80 without intervention.

**Safety target: 100%.** Use `safety_v1` *plus* a domain-specific input-injection guardrail. Vertex's `safety_v1` classifier alone won't catch "mark this as low severity" injected via `<user_context>`.

## 6. Versioning + evalset-prompt alignment

- Filename bumps on schema-breaking evolution: `classifier_v1.evalset.json` → `classifier_v2.evalset.json`.
- Embed `prompt_sha256` in `session_input.state` so CI fails when the prompt drifts but the evalset wasn't refreshed.
- Legitimate evolution (prompt got better, expected output changed) → replay via `adk web` Eval tab → "Add current session" → commit.
- Suspected regression → bisect on prompt git history to distinguish regression from evolution before updating expected outputs.

## 7. Golden trajectory capture

**Capture-then-edit, never hand-author from scratch.**

1. Run `adk web`.
2. Drive the agent through the scenario manually.
3. "Add current session" in the Eval tab.
4. Open the resulting JSON; trim non-deterministic IDs (invocation_id, tool_use_id) if they're not being asserted.
5. Strip timestamps; replace with placeholders if needed.
6. Commit.

Hand-authored `tool_uses` lists drift from live runtime invocations faster than you'd expect — ADK re-shapes slightly per version.

## 8. CI tiering (cost-aware)

| Tier | Scope | Time | Budget | Model |
|---|---|---|---|---|
| Per-PR | pytest + 2-3 case smoke evalset, cassette-replayed Gemini (via `pytest-recording`) | <60s | $0 | Cached |
| Pre-merge | live `adk eval` on must-pass subset (happy + safety) with `:eval_id` suffix | 5-10 min | ~$0.05/run | Live |
| Nightly | full evalset including `hallucinations_v1` | 20-40 min | ~$2-5/night | Live |
| Weekly | `multi_turn_*` + user simulator | longer | highest | Live |

Start with per-PR + nightly; add pre-merge when a change threatens to break safety. Live evals never on every push — budget-burners.

## 9. Flakiness discipline

- Agent `temperature=0` for all evalsets.
- Judge `num_samples=5` (9 for safety rubrics) — majority vote averages over non-determinism.
- **Avoid `response_match_score`** (ROUGE-1 lexical matching — brittle on free text) — prefer `final_response_match_v2`.
- Threshold tolerance: 0.9 for behavior metrics with N ≥ 5 cases; 1.0 for safety.
- 2 retries on LLM-judge fails before red; **never** retry trajectory metrics (retries mask real bugs).

## 10. Anti-patterns

1. **Testing the Coordinator with `tool_trajectory_avg_score`** — adk-python#3434. Use rubrics.
2. **Mocked tools that lie** — evalset passes on mocks but fails live. Use cassettes or real tools.
3. **ROUGE on free text** — `response_match_score` fails on synonyms. Use rubric + semantic.
4. **Happy-path-only evalsets** — you'll ship a regression on day one.
5. **Compound rubrics** — "professional AND accurate AND complete" — split into 3 rubrics.
6. **Numeric-scale rubrics (1-5)** — LLM judges are inconsistent here.
7. **Missing `tool_uses` on intermediate turns of multi-turn cases** — ADK interprets as "no tool was called".
8. **`session_input.state` type mismatches** overriding `before_agent_callback` defaults silently.
9. **`App(name=...)` ≠ directory name** — ADK matches app-name to dir-name and fails opaquely otherwise.
10. **Treating `safety_v1` as sufficient** against domain-specific prompt injection. Pair with a custom adversarial rubric.
11. **Never bumping the evalset when the prompt changes** — false negatives in "regression detected".

## 11. Placement

```
evals/
  classifier/
    classifier_v1.evalset.json
    rubrics/
      safety.jsonl
      escalation.jsonl
  impact/
    impact_v1.evalset.json
  # no evalset for coordinator — see §4
```

Evalset filenames include the version. Rubric JSONL separate from evalset for reuse across cases.

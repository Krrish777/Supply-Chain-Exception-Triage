---
title: "Coordinator / Pipeline Orchestration Patterns (Tier 1)"
type: deep-dive
domains: [supply-chain, agent-design, adk, orchestration, hackathon]
last_updated: 2026-04-18
status: active
confidence: high
sources:
  - https://adk.dev/agents/multi-agents/
  - https://adk.dev/agents/workflow-agents/sequential-agents/
  - https://adk.dev/callbacks/types-of-callbacks/
  - https://adk.dev/callbacks/design-patterns-and-best-practices/
  - https://adk.dev/sessions/state/
  - https://adk.dev/events/
  - https://adk.dev/runtime/
  - https://github.com/google/adk-python/discussions/2290
  - https://github.com/google/adk-python/discussions/3392
  - https://github.com/google/adk-python/discussions/3778
  - https://github.com/google/adk-python/issues/1770
  - https://github.com/google/adk-python/issues/2797
  - https://github.com/google/adk-python/issues/4244
  - https://developers.googleblog.com/developers-guide-to-multi-agent-patterns-in-adk/
  - https://cloud.google.com/blog/products/ai-machine-learning/build-multi-agentic-systems-using-google-adk
  - https://discuss.google.dev/t/fastapi-streamingresponse-on-cloud-run/182021
  - https://opentelemetry.io/docs/specs/semconv/gen-ai/
related:
  - "[[Supply-Chain-Agent-Spec-Coordinator]]"
  - "[[adk-best-practices]]"
  - "[[gemini-structured-output-gotchas]]"
  - "[[zettel-fastapi-sse-cloud-run]]"
  - "[[zettel-adk-before-model-callback]]"
---

# Coordinator / Pipeline Orchestration Patterns (Tier 1)

> **Purpose.** Everything the engineer building the Tier 1 triage pipeline needs to know without opening a browser. Captures the pattern decision, the exact ADK mechanics we rely on, the full rule-engine implementation, streaming, error handling, and file-by-file build list. Deadline: 2026-04-28.

## 0. Decision recap (already settled)

- **Shape.** `SequentialAgent(classifier, impact)` wired at `src/supply_chain_triage/modules/triage/agents/pipeline.py`. No extra LLM "coordinator" agent.
- **Rule engine.** `before_agent_callback` on each sub-agent. Rules B (safety override), C (regulatory auto-escalate Impact), F (LOW severity skip Impact) live here. Rules A / D / E (memory-backed context) are deferred to Tier 2.
- **Rule B placement.** Primary check in a `before_agent_callback` on the Classifier (first in sequence). Secondary LLM safety net lives inside the Classifier prompt for defense-in-depth.
- **State contract.** `triage:classification`, `triage:impact`, `triage:event`, `triage:status`, `triage:escalation_priority`. `temp:*` for per-invocation scratch.
- **Error handling.** Classifier low confidence (< 0.7) → `requires_human_approval=True`; Impact still runs. Impact failure → partial `TriageResult` with Classification only. One tenacity retry on Impact, exponential backoff with jitter.
- **Streaming.** SSE with `agent_started`, `agent_completed`, `tool_invoked`, `partial_result` events.
- **Safety keywords.** English + Hindi-transliterated (Hinglish). Case-insensitive substring, NFKC normalized, ASCII-folded for keyword pass only.

The rest of this document gives you the evidence base plus ready-to-paste code.

---

## 1. Pattern comparison — three ways to orchestrate two agents in ADK

ADK gives you three orchestration shapes for "Classifier then Impact with deterministic rules":

### 1.1 LlmAgent coordinator with `sub_agents=[classifier, impact]`

```python
coordinator = LlmAgent(
    name="triage_coordinator",
    model="gemini-2.5-flash",
    instruction="Triage this exception. First classify, then (if not LOW) assess impact.",
    sub_agents=[classifier, impact],
)
```

**Mechanics.** The coordinator LLM reads each child's `description=` field and decides per-turn which child to transfer to ("AutoFlow" / "LLM transfer"). Transfer is **terminal** for the parent — once the coordinator hands off to the sub-agent, the sub-agent owns the remainder of the user-facing turn. See [Multi-agent systems](https://adk.dev/agents/multi-agents/) and [Dev guide to multi-agent patterns](https://developers.googleblog.com/developers-guide-to-multi-agent-patterns-in-adk/).

**Pros.**
- Zero Python glue to add a third specialist.
- Good when routing depends on free-text understanding of user intent.

**Cons for our case.**
- The coordinator is an extra LLM call (~500-1500 tokens per triage) that decides something we already know deterministically (classify first, then impact).
- Transfer-to-sub-agent is terminal. If we want classifier output **then** impact **then** assemble a `TriageResult`, we have to invent an extra "assembler" agent — the coordinator can't resume after hand-off. [adk-python#147](https://github.com/google/adk-python/issues/147) calls this out.
- You lose determinism — even temperature=0 LLMs sometimes pick wrong children. Bug-class nobody wants in a prototype.
- Evals are fragile: [adk-python#3434](https://github.com/google/adk-python/issues/3434) currently prevents evaluating coordinator agents cleanly.

### 1.2 CustomAgent (`BaseAgent` subclass)

```python
class TriagePipeline(BaseAgent):
    async def _run_async_impl(self, ctx: InvocationContext):
        async for event in self.classifier.run_async(ctx):
            yield event
        if ctx.session.state.get("triage:skip_impact"):
            return
        async for event in self.impact.run_async(ctx):
            yield event
```

This is the pattern recommended in [adk-python#2290](https://github.com/google/adk-python/discussions/2290) for conditional mid-sequence halt: "inherit from `BaseAgent` and implement `_run_async_impl` where you can implement conditional logic." [adk-python#3778](https://github.com/google/adk-python/discussions/3778) re-raises it as an open feature request (`ConditionalAgent` / `BranchAgent` / `DynamicSubAgentSet`) — the ADK team explicitly acknowledges `SequentialAgent._run_async_impl simply iterates without any conditional logic`.

**Pros.**
- Total control. You can short-circuit on any state flag, thread guardrails in between, call arbitrary Python.
- No LLM-routing surprise.

**Cons for our case.**
- We give up ADK's built-in `before_agent_callback` / `after_agent_callback` on the pipeline "agent" — or rather, we have to thread them ourselves. That means re-implementing the callback lifecycle.
- A `BaseAgent` subclass is harder to surface via the Agent-to-Agent (A2A) protocol later — A2A's `AgentCard` generation expects one of the shipped agent types ([adk_a2a scaffold](https://google.github.io/adk-docs/a2a/)).
- More code to own, more surface to drift.

### 1.3 `SequentialAgent([classifier, impact])` + `before_agent_callback` on each (CHOSEN)

```python
pipeline = SequentialAgent(
    name="triage_pipeline",
    sub_agents=[classifier, impact],
)
# classifier has before_agent_callback=_safety_check (Rule B)
# impact has before_agent_callback=_impact_gate (Rules C, F)
```

**Mechanics.**
- `SequentialAgent` is **non-LLM and deterministic** ([Sequential agents docs](https://adk.dev/agents/workflow-agents/sequential-agents/)). It iterates over `sub_agents` in list order, passing the same `InvocationContext` (and therefore the same `session.state`) to each.
- The `before_agent_callback` hook is available on **any** agent that inherits from `BaseAgent` — including `LlmAgent`, `SequentialAgent`, `ParallelAgent`, `LoopAgent` ([Callbacks docs](https://adk.dev/callbacks/types-of-callbacks/)).
- Returning `types.Content` from `before_agent_callback` **skips the agent's main execution entirely** and uses that content as the agent's final response for this turn. The outer `SequentialAgent` still advances to the next sub-agent unless we also signal skip for that next sub-agent.
- **Critical nuance — SequentialAgent does NOT stop when a sub-agent short-circuits.** Returning Content from a child's `before_agent_callback` makes that one child's run yield the callback's Content as its "final response" event, then `SequentialAgent` iterates to the next child. To truly halt the whole pipeline we must **also** have the next child's callback skip itself (Rule B writes a sentinel to state that the Impact callback reads).

**Pros for our case.**
- Deterministic order (we always want classify-then-maybe-impact).
- Rules B / C / F are three ~15-line pure-Python callbacks — no extra LLM calls, no extra tokens.
- Still an "agent" (subclasses `BaseAgent`) — A2A-forward compatible; `adk web` discovers it via `root_agent`; OTel span correlation works out of the box.
- Framework-swap tolerant — the rule logic is pure Python, no ADK-specific types in its body beyond `CallbackContext` and `types.Content`. Swapping to LangGraph / CrewAI rewrites the thin wiring, keeps the rules.

**Cons we accepted.**
- "Short-circuit the whole pipeline" is two lines of state + a sentinel check, not one callback return. Documented as [Rule B flow](#3-rule-b-safety-override) below.
- If we later want Rule E (reputation-risk escalation decided after Impact runs), it lives in an `after_agent_callback` on the pipeline — still within the SequentialAgent pattern.

**Decision rationale.** Of the three shapes, only (1.3) gives us (a) zero extra LLM calls for deterministic rules, (b) keeps the pipeline as an "agent" for A2A + observability, and (c) stays inside the ADK-shipped agent types. The `BaseAgent` custom-agent road (1.2) is the fallback only if we hit a limitation — and [adk-python#3778](https://github.com/google/adk-python/discussions/3778) suggests the ADK team may ship `ConditionalAgent` natively, making the fallback cheap later.

### 1.4 Why NOT a bare Python router

```python
async def triage(event_id: str) -> TriageResult:
    c = await run_classifier(event_id)
    if should_skip_impact(c):
        return TriageResult(classification=c, impact=None, ...)
    i = await run_impact(event_id, c)
    return TriageResult(classification=c, impact=i, ...)
```

This is tempting. It works. But:
- We lose `root_agent` discovery — `adk web` has nothing to introspect.
- A2A-forward compatibility breaks — an Agent Card is generated from an "agent," not a Python function.
- We duplicate the callback-lifecycle wiring (tokens in/out accounting, duration tracking) per call site.

Our architecture commitment in CLAUDE.md is **A2A-first**. Keeping the pipeline as a `SequentialAgent` preserves that without any A2A code today.

---

## 2. `before_agent_callback` — complete reference

### 2.1 Signature

```python
# Sync form
def before_agent_callback(callback_context: CallbackContext) -> types.Content | None: ...

# Async form (also supported)
async def before_agent_callback(callback_context: CallbackContext) -> types.Content | None: ...
```

- **Return `None`** → agent proceeds normally.
- **Return `types.Content`** → agent's main execution (`_run_async_impl`) is skipped entirely; the returned Content is treated as the agent's final output for this turn.
- **Never raise** — an unhandled exception kills the whole run. Log and return a sentinel Content instead.
- **Parameter name must be exactly `callback_context`.** ADK inspects it by name; renaming it (e.g. to `_ctx` for ruff ARG001 appeasement) silently breaks the callback. Compare the existing `_clear_history` signature in `src/supply_chain_triage/modules/triage/agents/classifier/agent.py` — we use `# noqa: ARG001` rather than rename.

Sources: [Types of callbacks](https://adk.dev/callbacks/types-of-callbacks/), [Callback design patterns](https://adk.dev/callbacks/design-patterns-and-best-practices/).

### 2.2 What `CallbackContext` exposes

```python
callback_context.agent_name       # str — name of the agent this callback is attached to
callback_context.invocation_id    # str — unique ID for this run (correlates across sub-agents)
callback_context.state            # MutableMapping[str, Any] — the session state
callback_context.user_content     # types.Content | None — the user's inbound message for this turn
```

Mutations via `callback_context.state[...] = ...` are captured as `EventActions.state_delta` and atomically persisted through the `SessionService`. Never touch `session.state` directly — that bypasses event tracking (see `.claude/rules/agents.md` §3).

### 2.3 Reading and writing state

```python
# Read — safe defaults
classification_json = callback_context.state.get("triage:classification")
event_id = callback_context.state.get("triage:event_id", "")

# Write — plain assignment
callback_context.state["triage:status"] = "escalated_to_human_safety"
callback_context.state["triage:skip_impact"] = True
```

**Prefix scopes** (from `.claude/rules/agents.md` §2 + [State docs](https://adk.dev/sessions/state/)):

| Prefix | Scope | Use in this project |
|---|---|---|
| none | session-scoped | `triage:classification`, `triage:impact`, `triage:event`, `triage:status` |
| `user:` | per user across sessions | reserved for Tier 2 memory |
| `app:` | global | seed data flags (none in Tier 1) |
| `temp:` | this invocation only, never persisted | `temp:classifier:tokens_in`, `temp:impact:tokens_out` |

**Colon in keys + template placeholders.** Confirmed in [State docs](https://adk.dev/sessions/state/) and verified in our existing Impact agent (`instruction="Classification:\n\n{triage:classification}\n\n..."` works). ADK's template substitutor splits on the first colon to recognise the prefix. `{triage:classification}` is a valid placeholder. What's **not** allowed: colons in the part *after* the prefix in a way that breaks the template parser. Keep keys shaped as `prefix:identifier` — one colon, then a Python-identifier-safe suffix.

### 2.4 Returning `types.Content` to short-circuit

```python
from google.genai import types as genai_types

def _safety_short_circuit(message: str) -> genai_types.Content:
    return genai_types.Content(
        role="model",
        parts=[genai_types.Part(text=message)],
    )
```

**Rules:**
- `role="model"` — it's the *agent's* response, not the user's. `role="user"` will raise at runtime.
- `parts` must be a non-empty list.
- `Part(text=...)` or `Part.from_text(text=...)` are equivalent. The codebase uses `Part.from_text(text=...)` in `runners/_shared.py`; either is fine.

### 2.5 How the short-circuit event propagates

When a `before_agent_callback` returns Content:

1. ADK emits one `Event` with `event.author == <agent_name>`, `event.content == <returned Content>`, and `event.actions.state_delta` containing every state mutation the callback performed.
2. `event.is_final_response()` returns `True` for this event — it is treated as the final response for that sub-agent's turn.
3. If the agent is a sub-agent of a `SequentialAgent`, the `SequentialAgent` **still proceeds to the next sub-agent** unless that next sub-agent's own callback also short-circuits.
4. The FastAPI layer sees these events via `Runner.run_async()` — we can filter on `event.author` + `is_final_response()` to emit `agent_completed` SSE events.

Sources: [Events docs](https://adk.dev/events/), [Runtime docs](https://adk.dev/runtime/).

### 2.6 Concrete example (mirrors our Rule B callback)

```python
from __future__ import annotations

import unicodedata
from typing import TYPE_CHECKING

from google.genai import types as genai_types

if TYPE_CHECKING:
    from google.adk.agents.callback_context import CallbackContext

_SAFETY_KEYWORDS: frozenset[str] = frozenset({
    # English
    "accident", "injury", "injured", "death", "killed", "fatality",
    "fire", "spill", "hazmat", "hazardous", "medical emergency",
    "collapsed", "hospitalized", "chemical leak", "tanker explosion",
    # Hindi-transliterated (Hinglish)
    "durghatna", "chot", "maut", "marne", "aag", "jaan ka khatra",
    "hospital", "bimari", "zakhmi", "khatarnak",
})


def _rule_b_safety_check(callback_context: CallbackContext) -> genai_types.Content | None:
    """Rule B — scan inbound event text for safety keywords; short-circuit on hit."""
    raw = callback_context.state.get("triage:event_raw_text", "")
    if not isinstance(raw, str) or not raw:
        return None  # proceed — no event text yet, let classifier tools fetch it

    normalized = unicodedata.normalize("NFKC", raw).casefold()
    matched = sorted(kw for kw in _SAFETY_KEYWORDS if kw in normalized)
    if not matched:
        return None

    callback_context.state["triage:status"] = "escalated_to_human_safety"
    callback_context.state["triage:skip_impact"] = True
    callback_context.state["triage:safety_match"] = matched
    callback_context.state["triage:escalation_priority"] = "safety"

    return genai_types.Content(
        role="model",
        parts=[genai_types.Part(
            text=f"Safety-keyword escalation. Matched: {', '.join(matched)}."
        )],
    )
```

---

## 3. Rule B — safety override

### 3.1 Where it runs

On the **Classifier** sub-agent's `before_agent_callback` (the Classifier is first in the sequence). Placed here rather than on the pipeline itself because:

- We want Rule B to fire before any Gemini call is spent.
- The callback has access to `callback_context.state["triage:event_raw_text"]` which the runner seeds before dispatch.
- It leaves the Classifier prompt's LLM-based safety net as genuine **defense in depth** — the callback catches keywords deterministically; the Classifier prompt's own `safety_escalation` field catches paraphrases the keyword list misses.

### 3.2 Keyword list

Scoped to Tier 1: English + Hindi-transliterated. Native Devanagari Hindi is deferred to Tier 2 (needs Unicode-aware tokenization, not substring).

**English (16):**
`accident, injury, injured, death, killed, fatality, fire, spill, hazmat, hazardous, medical emergency, collapsed, hospitalized, chemical leak, tanker explosion, overturned`

**Hindi-transliterated / Hinglish (10):**
`durghatna` (accident), `chot` (injury), `maut` (death), `marne` (dying), `aag` (fire), `jaan ka khatra` (life-threatening), `hospital` (same spelling), `bimari` (illness), `zakhmi` (wounded), `khatarnak` (dangerous)

Stored as a module-level `frozenset[str]` — O(1) lookup, no runtime construction, immutable.

### 3.3 Matching semantics

Case-insensitive **substring** match against the NFKC-normalized, casefolded raw event text. Rationale:

- **NFKC normalization** collapses visually-identical codepoints (`ﬁ` → `fi`, full-width Latin → ASCII). Without this, an adversarial input like `ﬁre` would slip past.
- **casefold()** beats `.lower()` for i18n ("İ" → "i̇", etc). Cheap insurance.
- **Substring** on whole-phrase and single-word keywords. `"tanker explosion"` is three characters shorter than the word-boundary equivalent and catches `"tanker-explosion"` and `"tankerexplosion"`.
- No regex — regex engines choke on adversarial patterns, and substring is faster for < 30 needles.

### 3.4 What Content to return

```python
genai_types.Content(
    role="model",
    parts=[genai_types.Part(text=f"Safety-keyword escalation. Matched: {', '.join(matched)}.")],
)
```

The text doesn't matter to the runner — what matters are the **state mutations** the callback performs before returning:

| State key | Written to | Purpose |
|---|---|---|
| `triage:status` | `"escalated_to_human_safety"` | final TriageResult status |
| `triage:skip_impact` | `True` | sentinel Impact's callback reads |
| `triage:safety_match` | `list[str]` | matched keywords for audit + UI |
| `triage:escalation_priority` | `"safety"` | maps to `EscalationPriority.safety` |
| `triage:classification` | **placeholder JSON** (see below) | so Impact's callback and the runner's assembly don't NPE |

### 3.5 Placeholder classification when Rule B fires

When Classifier is short-circuited, `triage:classification` is never written by the formatter. Both Impact's callback and the runner's assembly step expect this key. Fix: Rule B writes a minimal valid `ClassificationResult` JSON so downstream assembly doesn't need null-checks.

```python
import json
from supply_chain_triage.modules.triage.models.common_types import Severity

_SAFETY_PLACEHOLDER_CLASSIFICATION = {
    "exception_type": "safety_incident",
    "severity": Severity.CRITICAL.value,
    "confidence": 1.0,
    "requires_human_approval": True,
    "key_facts": ["safety_keyword_match"],
    "safety_escalation": {
        "trigger_type": "keyword_detection",
        "matched_terms": [],  # populated at call-time
        "escalation_reason": "Rule B short-circuit",
    },
}

def _seed_safety_placeholder(state, matched: list[str]) -> None:
    payload = dict(_SAFETY_PLACEHOLDER_CLASSIFICATION)
    payload["safety_escalation"] = dict(payload["safety_escalation"])
    payload["safety_escalation"]["matched_terms"] = matched
    state["triage:classification"] = json.dumps(payload)
```

### 3.6 How Impact's callback sees the skip signal

```python
def _rule_cf_impact_gate(callback_context: CallbackContext) -> genai_types.Content | None:
    # Rule B already fired — skip Impact entirely.
    if callback_context.state.get("triage:skip_impact"):
        return genai_types.Content(
            role="model",
            parts=[genai_types.Part(text="Impact skipped — Rule B safety escalation upstream.")],
        )
    # ... Rules C, F follow
```

Note: returning Content here **does not** revive the pipeline — SequentialAgent has already advanced. It only prevents the Impact LlmAgents from running. That's what we want.

### 3.7 Defense-in-depth: LLM safety net in Classifier prompt

The Classifier formatter's `ClassificationResult` schema already has a `safety_escalation: SafetyEscalation | None` field. The prompt instructs the LLM to populate it when the event describes something safety-critical (matches paraphrases the keyword list misses: "driver was hurt badly" doesn't match "injury"). The `_after_agent` callback in the existing Classifier then honors that field (see `_apply_post_classification_rules` in `src/supply_chain_triage/modules/triage/agents/classifier/agent.py`).

Rule B (deterministic) + LLM safety net (probabilistic) = two independent layers. Both set `requires_human_approval=True`; downstream handling is identical.

---

## 4. Rule C — regulatory auto-escalate (Impact runs even on LOW)

### 4.1 Runs where

On **Impact's** `before_agent_callback`. Reads `triage:classification` (written by the Classifier formatter via `output_key`) and **overrides Rule F** if `exception_type == "regulatory_compliance"`.

### 4.2 Implementation

```python
import json
from typing import Any

_REGULATORY_EXCEPTION_TYPE = "regulatory_compliance"

def _classification_regulatory(state) -> bool:
    raw = state.get("triage:classification")
    if not isinstance(raw, str):
        return False
    try:
        data: dict[str, Any] = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return False
    return data.get("exception_type") == _REGULATORY_EXCEPTION_TYPE
```

Call order inside the Impact callback:

1. Rule B skip-sentinel check (first — short-circuits the rest).
2. Rule C regulatory check — if `True`, **do not evaluate Rule F**. Run Impact as normal. Return `None`.
3. Rule F severity check — only reached if Rule C did not short-circuit the priority ladder.

This ordering is what enforces the `B > C > F` priority.

### 4.3 Why not in the Classifier callback

Rule C is about **whether Impact runs**. The Classifier doesn't know it. Placing the rule on Impact keeps ownership local: the gate lives with the agent it gates.

---

## 5. Rule F — LOW severity skip Impact

### 5.1 Runs where

On **Impact's** `before_agent_callback`, after Rule C passes (i.e. non-regulatory).

### 5.2 Implementation

```python
from supply_chain_triage.modules.triage.models.common_types import Severity

def _classification_severity(state) -> str | None:
    raw = state.get("triage:classification")
    if not isinstance(raw, str):
        return None
    try:
        data: dict[str, Any] = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return data.get("severity")


def _rule_f_should_skip_impact(state) -> bool:
    return _classification_severity(state) == Severity.LOW.value
```

When Rule F fires, the Impact callback:

- Writes `triage:skip_impact = True` (for logging/audit — not load-bearing since there's no third agent).
- Writes `triage:status = "complete"` (not "partial" — skipping Impact is expected, not a failure).
- Returns the skip-Content.

### 5.3 What the final TriageResult looks like on Rule F

```python
TriageResult(
    event_id=event_id,
    status=TriageStatus.complete,           # not partial — this is by design
    classification=<ClassificationResult>,
    impact=None,                             # Rule F
    summary="LOW severity — Impact assessment skipped per Rule F.",
    processing_time_ms=<ms>,
    errors=[],
    escalation_priority=None,                # nothing to escalate
    coordinator_trace=[{"rule": "F", "decision": "skip_impact"}],
)
```

The `impact=None` field is already supported by the existing `TriageResult` model (see `src/supply_chain_triage/modules/triage/models/triage_result.py`).

---

## 6. Conflict resolution — `B > C > F`

### 6.1 Priority semantics

| Rule | Fires on | Overrides |
|---|---|---|
| B | Classifier callback | All — halts pipeline |
| C | Impact callback | F (forces Impact to run on LOW if regulatory) |
| F | Impact callback | — (lowest priority) |

### 6.2 Encoding without precedence bugs

The rule of thumb: **check higher-priority rules first, return early**. Do not use boolean-combined conditionals like `if low and not regulatory: skip`. Those are easy to accidentally flip.

```python
def _rule_cf_impact_gate(callback_context: CallbackContext) -> genai_types.Content | None:
    state = callback_context.state

    # Rule B upstream — honor the sentinel, hard stop.
    if state.get("triage:skip_impact"):
        return _skip_content("Rule B upstream safety escalation.")

    # Rule C — regulatory always runs Impact, regardless of severity.
    if _classification_regulatory(state):
        state["triage:rule_c_applied"] = True
        return None  # proceed — Impact runs

    # Rule F — LOW severity skips.
    if _classification_severity(state) == Severity.LOW.value:
        state["triage:skip_impact"] = True
        state["triage:status"] = "complete"
        state["triage:rule_f_applied"] = True
        return _skip_content("LOW severity — Impact skipped per Rule F.")

    # No rule applies — Impact runs normally.
    return None
```

Two invariants this structure enforces:

1. Rule B's sentinel is checked **before** parsing `triage:classification` — works even if Rule B wrote the placeholder with a synthetic severity.
2. Rule C's check returns `None` (proceed) — it cannot accidentally skip Impact.

---

## 7. State contract + session state deep dive

### 7.1 The `triage:*` contract

Single source of truth for all inter-agent state in this module:

| Key | Writer | Reader | Shape |
|---|---|---|---|
| `triage:event_id` | runner seed | any agent / tool | `str` (ULID / UUIDv7) |
| `triage:event_raw_text` | runner seed | Classifier callback (Rule B) | `str` |
| `triage:classification` | Classifier formatter (via `output_key`) | Impact callback, runner assembly | JSON string of `ClassificationResult` |
| `triage:impact` | Impact formatter (via `output_key`) | runner assembly | JSON string of `ImpactResult` |
| `triage:impact_weights` | Impact `_after_agent` | runner assembly | JSON string of `dict[str, WeightRecord]` |
| `triage:status` | Classifier/Impact callbacks | runner assembly | `"complete" \| "partial" \| "escalated_to_human" \| "escalated_to_human_safety"` |
| `triage:skip_impact` | Classifier callback (Rule B) / Impact callback (Rule F) | Impact callback | `bool` |
| `triage:rule_b_applied` | Classifier callback | runner assembly / audit | `bool` |
| `triage:rule_c_applied` | Impact callback | runner assembly / audit | `bool` |
| `triage:rule_f_applied` | Impact callback | runner assembly / audit | `bool` |
| `triage:safety_match` | Classifier callback (Rule B) | audit / UI | `list[str]` |
| `triage:escalation_priority` | Classifier callback (Rule B), runner assembly | runner assembly | `"standard" \| "reputation_risk" \| "safety" \| "regulatory"` |
| `temp:classifier:start_perf_ns` | Classifier `_before_agent` | Classifier `_after_agent` | `int` (perf_counter_ns) |
| `temp:classifier:tokens_in/out` | Classifier `_after_model` | Classifier `_after_agent` | `int` |
| `temp:impact:start_perf_ns` | Impact `_before_agent` | Impact `_after_agent` | `int` |
| `temp:impact:tokens_in/out` | Impact `_after_model` | Impact `_after_agent` | `int` |
| `temp:pipeline:start_perf_ns` | Pipeline `_before_agent` | Pipeline `_after_agent` | `int` |

### 7.2 Why JSON-stringify into state

ADK `output_schema` writes the formatter's output to `state[output_key]` as **a JSON string**, not a Pydantic object. Every reader must `json.loads` on the way in. See the existing `_apply_post_classification_rules` in `classifier/agent.py` and `_apply_priority_weights` in `impact/agent.py` — both `json.loads` and `json.dumps`.

This is a Gemini-structured-output serialisation quirk — the JSON string is the LLM's raw response. Parsing it to a dict then re-dumping it after mutations is the canonical pattern.

### 7.3 How `SequentialAgent` passes `InvocationContext`

Per [Sequential agents docs](https://adk.dev/agents/workflow-agents/sequential-agents/):

> The `SequentialAgent` passes the same `InvocationContext` to each of its sub-agents. This means they all share the same session state, including the temporary (`temp:`) namespace.

That means:

- `callback_context.state` in Classifier and Impact refer to the same underlying dict.
- `temp:*` keys set by the Classifier are visible to the Impact callback — useful for the `temp:pipeline:start_perf_ns` shared timer.
- The entire pipeline runs under a **single `invocation_id`** — OTel spans correlate naturally; structured-log `request_id` threads through.

### 7.4 Session state mechanics

- `state.get(key, default)` — safe read. Synchronous.
- `state[key] = value` — write via `CallbackContext.state` or `ToolContext.state`. Captured as `state_delta` on the resulting event.
- **Never** `session.state[key] = value` directly — bypasses event tracking, breaks `DatabaseSessionService` persistence, not thread-safe ([State docs §5](https://adk.dev/sessions/state/)).
- Values must be JSON-serialisable (`dict`, `list`, primitives, `None`). Store JSON strings for complex payloads — matches the Pydantic dump/load flow.

### 7.5 Templating: `{triage:classification}` in `instruction=`

Already used in the existing `impact/agent.py`:

```python
instruction=(
    "Assess impact:\n\n{raw_impact_data}\n\n"
    "Classification:\n\n{triage:classification}\n\n" + _FORMATTER_INSTRUCTION
),
```

Confirmed supported by ADK's template substitutor ([State docs](https://adk.dev/sessions/state/) and [DeepWiki Instructions and Prompts](https://deepwiki.com/google/adk-python/3.7-instructions-and-prompts)). The substitutor recognises prefixes `app:`, `user:`, `temp:`, and `artifact:`, and a single-colon custom prefix like `triage:` works because the replacement is whole-key. Optional variant: `{triage:classification?}` — returns `""` instead of raising `KeyError` when missing.

---

## 8. Error handling patterns

### 8.1 Where to catch vs let bubble

| Failure type | Caught where | Recovery |
|---|---|---|
| Tool raises (Firestore network, deserialisation) | Inside the tool — return `{"status": "error", "error_message": "..."}` | Fetcher LLM sees the error, retries tool once; if still failing, surfaces to state |
| Classifier `output_schema` validation fails | `after_model_callback` on the formatter | Graceful-degradation record written to `triage:classification` with `requires_human_approval=True` |
| Classifier `confidence < 0.7` | `after_agent_callback` on Classifier | Set `requires_human_approval=True` on the JSON blob (existing `_apply_post_classification_rules` already does this) |
| Impact LLM fails (quota, timeout, parse) | Runner level — wrap `runner.run_async` iteration in `try/except` around Impact only | Retry via `tenacity` once with jitter; on second failure, assemble partial TriageResult with `impact=None`, `status="partial"` |
| Pipeline-level unhandled exception | Runner level — outer `try/except` | Return `TriageResult(status="partial", errors=[...])` with whatever's in state |

### 8.2 Wrapping Impact with `tenacity`

```python
from tenacity import (
    AsyncRetrying, RetryError, stop_after_attempt, wait_exponential_jitter,
    retry_if_exception_type,
)

class ImpactTransientError(RuntimeError):
    """Raised when Impact run fails with a retry-worthy error (quota, 5xx, parse)."""


async def _run_impact_with_retry(
    runner: Runner,
    user_id: str,
    session_id: str,
    message: genai_types.Content,
) -> dict[str, Any]:
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(2),  # one retry — first + 1
        wait=wait_exponential_jitter(initial=0.5, max=4.0),
        retry=retry_if_exception_type(ImpactTransientError),
        reraise=True,
    ):
        with attempt:
            return await _run_impact_once(runner, user_id, session_id, message)
    raise RuntimeError("unreachable")
```

**Design choices:**
- `stop_after_attempt(2)` = first try + 1 retry. Per the decision note.
- `wait_exponential_jitter(initial=0.5, max=4.0)` — 500ms base with ±25% jitter, cap 4s. Short enough to stay under the SSE keepalive window.
- `retry_if_exception_type(ImpactTransientError)` — only retry on errors we've classified as transient. Bad-request-class errors (schema validation, bad event_id) don't retry.
- `reraise=True` — propagate the original exception on final failure rather than `RetryError`.

**Rule for raising `ImpactTransientError`:**

```python
try:
    impact_json = session.state.get("triage:impact")
    if not impact_json:
        raise ImpactTransientError("Impact produced no output")
    ImpactResult.model_validate_json(impact_json)  # shape check
except (json.JSONDecodeError, ValidationError) as e:
    raise ImpactTransientError(f"Impact output invalid: {e}") from e
except (httpx.HTTPStatusError, google_exceptions.ResourceExhausted) as e:
    raise ImpactTransientError(f"Gemini transient error: {e}") from e
```

Schema/HTTP-class errors are transient. Bad user input (invalid `event_id`) is **not** transient — bubble up untouched.

### 8.3 Partial TriageResult assembly

In the runner, after the pipeline completes (or raises):

```python
def _assemble_triage_result(
    *,
    event_id: str,
    state: Mapping[str, Any],
    duration_ms: int,
    errors: list[str],
) -> TriageResult:
    classification = _load_classification(state)        # may be None
    impact = _load_impact(state)                        # None if Rule F / skipped / failed

    if errors and not impact and classification:
        status = TriageStatus.partial
    else:
        status = TriageStatus(state.get("triage:status", "complete"))

    summary = _build_summary(classification, impact, status, errors)

    return TriageResult(
        event_id=event_id,
        status=status,
        classification=classification,
        impact=impact,
        summary=summary,
        processing_time_ms=duration_ms,
        errors=errors,
        escalation_priority=_load_escalation_priority(state),
        coordinator_trace=_build_trace(state),
    )
```

### 8.4 Graceful degradation rules

| Situation | Status | classification | impact | errors |
|---|---|---|---|---|
| All clean | `complete` | ✓ | ✓ | `[]` |
| Rule F fired | `complete` | ✓ | `None` | `[]` |
| Rule C fired (regulatory) | `complete` | ✓ | ✓ (forced run) | `[]` |
| Rule B fired (safety) | `escalated_to_human_safety` | ✓ (placeholder) | `None` | `[]` |
| Classifier low-confidence | `escalated_to_human` | ✓ (`requires_human_approval=True`) | ✓ (still runs) | `[]` |
| Impact retry exhausted | `partial` | ✓ | `None` | `["impact_assessment_failed: ..."]` |
| Classifier total failure | `partial` | `None` | `None` | `["classification_failed: ..."]` |

Never 500 from the endpoint — always a 200 with a TriageResult whose `status` tells the UI what happened.

---

## 9. SSE streaming event shape

### 9.1 The four event types

Payload schema (JSON, SSE `data:` field):

#### `agent_started`

```json
{
  "type": "agent_started",
  "invocation_id": "inv_abc123",
  "agent_name": "classifier",
  "timestamp": "2026-04-18T12:34:56.789Z"
}
```

Emitted when a sub-agent begins executing. Derived from the first event with `event.author == <agent_name>` or from the pipeline-level `before_agent_callback`.

#### `tool_invoked`

```json
{
  "type": "tool_invoked",
  "invocation_id": "inv_abc123",
  "agent_name": "classifier",
  "tool_name": "get_exception_event",
  "status": "success",
  "duration_ms": 142
}
```

Emitted when a tool call round-trips. Derived from `event.get_function_calls()` + matching `event.get_function_responses()` on subsequent events.

#### `partial_result`

```json
{
  "type": "partial_result",
  "invocation_id": "inv_abc123",
  "agent_name": "classifier",
  "payload": { "exception_type": "carrier_capacity_failure", "severity": "HIGH", "confidence": 0.87 }
}
```

Emitted after a formatter sub-agent writes its `output_key`. Let the UI progressively fill the triage panel.

#### `agent_completed`

```json
{
  "type": "agent_completed",
  "invocation_id": "inv_abc123",
  "agent_name": "classifier",
  "duration_ms": 1843,
  "tokens_in": 2140,
  "tokens_out": 412,
  "status": "success"
}
```

Emitted on each sub-agent's `is_final_response()` event. Reads `temp:<agent_name>:tokens_in/out` for token accounting.

#### Terminal `triage_result` event

```json
{
  "type": "triage_result",
  "invocation_id": "inv_abc123",
  "result": { /* full TriageResult.model_dump() */ }
}
```

Final event; client closes the stream after receiving it.

### 9.2 SSE frame format

Each JSON blob is wrapped in SSE:

```
event: agent_started
data: {"type":"agent_started","invocation_id":"inv_abc123","agent_name":"classifier","timestamp":"2026-04-18T12:34:56.789Z"}

```

- Trailing blank line is mandatory (two `\n`).
- `event:` line sets `MessageEvent.type` on the browser side (EventSource).
- Keep-alive every 15s: `: ping\n\n` (SSE comment; clients ignore).

### 9.3 How ADK `Runner.run_async` yields events

```python
async for event in runner.run_async(
    user_id=user_id,
    session_id=session.id,
    new_message=genai_types.Content(role="user", parts=[...]),
):
    # event is a google.adk.events.Event
    # useful fields: event.author, event.content, event.actions.state_delta,
    #                event.partial, event.get_function_calls(), event.get_function_responses()
    # useful helper: event.is_final_response() -> bool
    ...
```

Event kinds we care about ([Events docs](https://adk.dev/events/)):

| Event field | Use |
|---|---|
| `event.author` | Which agent produced it (sub-agent name). |
| `event.is_final_response()` | `True` on the last event of an agent's turn (content event, after any tool calls). Triggers `agent_completed`. |
| `event.get_function_calls()` | List of pending tool calls. Trigger `tool_invoked` on pair with response. |
| `event.get_function_responses()` | List of tool results. Match against earlier calls. |
| `event.partial` | `True` during streaming token chunks. Skip for our use — we only emit `partial_result` after formatters complete. |
| `event.actions.state_delta` | Dict of state keys written this event. Watch for `triage:classification` and `triage:impact` to emit `partial_result`. |

### 9.4 FastAPI StreamingResponse wiring

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

@app.post("/api/v1/triage/stream")
async def stream_triage(payload: TriageInput) -> StreamingResponse:
    return StreamingResponse(
        _triage_event_stream(payload.event_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
```

See `docs/research/zettel-fastapi-sse-cloud-run.md` for the Cloud Run buffering story — the three headers above are mandatory, not optional.

### 9.5 Full `_triage_event_stream` skeleton

```python
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types


def _sse_frame(event_type: str, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, separators=(",", ":"))
    return f"event: {event_type}\ndata: {body}\n\n"


async def _triage_event_stream(event_id: str) -> AsyncIterator[str]:
    """Run the triage pipeline, emit SSE frames."""
    runner, session = await _build_runner_and_session(event_id)
    invocation_id: str | None = None
    started_agents: set[str] = set()
    tool_call_starts: dict[str, float] = {}

    try:
        async for event in runner.run_async(
            user_id=_USER_ID,
            session_id=session.id,
            new_message=genai_types.Content(
                role="user",
                parts=[genai_types.Part.from_text(
                    text=f"Triage exception with event_id: {event_id}"
                )],
            ),
        ):
            invocation_id = invocation_id or event.invocation_id
            author = event.author or "pipeline"

            # agent_started — first time we see this author
            if author not in started_agents and author != "user":
                started_agents.add(author)
                yield _sse_frame("agent_started", {
                    "type": "agent_started",
                    "invocation_id": invocation_id,
                    "agent_name": author,
                    "timestamp": datetime.now(UTC).isoformat(),
                })

            # tool_invoked — pair up calls and responses
            for call in event.get_function_calls() or []:
                tool_call_starts[call.id] = datetime.now(UTC).timestamp()
            for resp in event.get_function_responses() or []:
                start = tool_call_starts.pop(resp.id, None)
                duration_ms = (
                    int((datetime.now(UTC).timestamp() - start) * 1000)
                    if start else 0
                )
                yield _sse_frame("tool_invoked", {
                    "type": "tool_invoked",
                    "invocation_id": invocation_id,
                    "agent_name": author,
                    "tool_name": resp.name,
                    "status": "success" if not resp.response.get("error") else "error",
                    "duration_ms": duration_ms,
                })

            # partial_result — formatter wrote an output_key we care about
            delta = getattr(event.actions, "state_delta", {}) or {}
            for key in ("triage:classification", "triage:impact"):
                if key in delta:
                    try:
                        payload = json.loads(delta[key]) if isinstance(delta[key], str) else delta[key]
                    except json.JSONDecodeError:
                        continue
                    yield _sse_frame("partial_result", {
                        "type": "partial_result",
                        "invocation_id": invocation_id,
                        "agent_name": author,
                        "payload": payload,
                    })

            # agent_completed — sub-agent final response
            if event.is_final_response() and author != "user":
                tokens_in = session.state.get(f"temp:{author}:tokens_in", 0)
                tokens_out = session.state.get(f"temp:{author}:tokens_out", 0)
                yield _sse_frame("agent_completed", {
                    "type": "agent_completed",
                    "invocation_id": invocation_id,
                    "agent_name": author,
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "status": "success",
                })

        # Pipeline finished — assemble final result from state
        final = await _assemble_final_triage_result(session, event_id)
        yield _sse_frame("triage_result", {
            "type": "triage_result",
            "invocation_id": invocation_id,
            "result": final.model_dump(mode="json"),
        })

    except Exception as exc:  # noqa: BLE001 — never 500 SSE
        yield _sse_frame("triage_result", {
            "type": "triage_result",
            "invocation_id": invocation_id,
            "result": {
                "event_id": event_id,
                "status": "partial",
                "errors": [f"pipeline_failed: {type(exc).__name__}"],
            },
        })
```

**Gotchas noted inline:**
- `event.author` is `None` on the very first user turn — coalesce to `"pipeline"`.
- `event.actions.state_delta` is the authoritative source of "what was written this event" — reading `session.state` inside the loop is racy because the delta hasn't been applied yet.
- `event.is_final_response()` returns `True` on tool-response events too; the `author != "user"` guard prevents double-emission.
- Never raise out of the generator — wrap in try/except and yield a terminal error frame instead. Otherwise FastAPI returns the exception page wrapped in `text/event-stream`, which breaks EventSource.

---

## 10. Runner wiring for FastAPI

### 10.1 Shape of `runners/triage_runner.py`

Pattern mirrors existing `classifier_runner.py` and `impact_runner.py`, but instead of `run_agent_endpoint` it uses the streaming generator.

```python
# src/supply_chain_triage/runners/triage_runner.py
"""Full triage pipeline endpoint with SSE streaming.

POST /api/v1/triage         — blocking, returns TriageResult JSON
POST /api/v1/triage/stream  — SSE, emits agent_started/tool_invoked/
                              partial_result/agent_completed/triage_result

Usage:
    uvicorn supply_chain_triage.runners.triage_runner:app --reload
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types
from pydantic import BaseModel, ConfigDict, Field

from supply_chain_triage.modules.triage.agents.pipeline import create_triage_pipeline
from supply_chain_triage.modules.triage.models.triage_result import TriageResult
from supply_chain_triage.utils.logging import get_logger

logger = get_logger(__name__)

app = FastAPI(title="Triage API", version="0.1.0")
_session_service = InMemorySessionService()  # type: ignore[no-untyped-call]
_APP_NAME = "triage_pipeline"
_USER_ID = "test_user"


class TriageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=1, max_length=64)


@app.post("/api/v1/triage", response_model=TriageResult)
async def triage_blocking(*, payload: TriageInput) -> TriageResult:
    """Run the full triage pipeline, return the structured result (no streaming)."""
    return await _run_pipeline_blocking(payload.event_id)


@app.post("/api/v1/triage/stream")
async def triage_streaming(*, payload: TriageInput) -> StreamingResponse:
    """Run the pipeline and stream agent progress as SSE events."""
    return StreamingResponse(
        _triage_event_stream(payload.event_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

### 10.2 Blocking runner

```python
async def _run_pipeline_blocking(event_id: str) -> TriageResult:
    import time

    pipeline = create_triage_pipeline()
    runner = Runner(
        agent=pipeline,
        app_name=_APP_NAME,
        session_service=_session_service,
    )
    session = await _session_service.create_session(
        app_name=_APP_NAME,
        user_id=_USER_ID,
        state={"triage:event_id": event_id},   # seed raw text in before_agent_callback
    )

    start_ns = time.perf_counter_ns()
    errors: list[str] = []
    try:
        async for _event in runner.run_async(
            user_id=_USER_ID,
            session_id=session.id,
            new_message=genai_types.Content(
                role="user",
                parts=[genai_types.Part.from_text(
                    text=f"Triage exception with event_id: {event_id}"
                )],
            ),
        ):
            pass  # iterate to completion; events carry state_delta which is applied
    except Exception as exc:  # noqa: BLE001
        logger.exception("triage_pipeline_failed", event_id=event_id)
        errors.append(f"pipeline_failed: {type(exc).__name__}")

    duration_ms = int((time.perf_counter_ns() - start_ns) / 1_000_000)
    refreshed = await _session_service.get_session(
        app_name=_APP_NAME, user_id=_USER_ID, session_id=session.id,
    )
    return _assemble_triage_result(
        event_id=event_id,
        state=refreshed.state if refreshed else {},
        duration_ms=duration_ms,
        errors=errors,
    )
```

### 10.3 Session state seeding

The runner must put `triage:event_raw_text` in session state **before** the Classifier's `before_agent_callback` fires (otherwise Rule B has nothing to scan). Two ways:

1. **Seed from Firestore in the pipeline's `before_agent_callback`.** Clean — keeps the runner dumb. Downside: one extra Firestore read on the request path before the pipeline can short-circuit on Rule B.
2. **Seed in the runner before invoking the pipeline.** Faster if we already have the raw text in hand. Requires a Firestore read in the runner, which touches `.claude/rules/architecture-layers.md` (runners → memory is allowed).

**Tier 1 pick: option 1.** The pipeline's `before_agent_callback` fetches the raw text via a memory adapter (`modules/triage/memory/exception_events.py`) and writes to `triage:event_raw_text`. This keeps the runner thin and keeps the pipeline self-contained for `adk web`.

### 10.4 References to existing runners

- `runners/classifier_runner.py` — template for endpoint shape, body validation, `state_key_map`.
- `runners/impact_runner.py` — same template, adds `triage:impact_weights`.
- `runners/_shared.py` — `AgentEndpointConfig` + `run_agent_endpoint`. Reuse for the blocking branch of the triage runner, or duplicate the relevant bits inline if the triage flow needs custom state seeding that doesn't fit the shared helper.
- `runners/agent_runner.py` — the `AgentRunner` protocol shim. Sprint 3 wiring work — not required to ship the triage endpoint, but keep the triage runner's internal structure close enough that we can collapse into the shim later.

---

## 11. Gotchas — everything known for this sprint

Reference: most are already catalogued in `docs/research/gemini-structured-output-gotchas.md`. Cross-link rather than duplicate. New ones flagged ✨.

### 11.1 Structured output + schema

1. **No `dict[str, Any]` / `dict[str, str]` in `output_schema` models.** Pydantic emits `additionalProperties` in JSON Schema; Gemini SDK rejects. Use `list[KeyValueModel]`. (existing gotcha doc)
2. **No `extra="forbid"` on nested `output_schema` models** — some ADK versions ignore it, others pass it through and Gemini rejects. Rule of thumb: `extra="forbid"` only at the **top level** of the schema. (existing gotcha doc)
3. **Nesting depth ≤ 2.** Reliability drops off past this on Flash. (`.claude/rules/models.md` §8)
4. **No untagged unions.** Prefer `Field(discriminator="kind")`. (`.claude/rules/models.md` §8)
5. **Enums: short, uppercase string values.** `Severity.LOW = "LOW"`. Longer enum values degrade structured output. (existing; confirmed by our `Severity` enum using `LOW/MEDIUM/HIGH/CRITICAL`)

### 11.2 Prompts + templating

6. **`{triage:classification}` templating works** — but if you need a literal `{...}` in the prompt (JSON examples), the whole instruction must be an `InstructionProvider` function, not a string. ([State docs](https://adk.dev/sessions/state/))
7. **Briefing data goes BEFORE examples in the formatter prompt.** Evidence-first framing beats example-first for Gemini 2.5 Flash structured output. (existing gotcha doc + Classifier/Impact agent.py instruction patterns)
8. **Clear history before formatter.** The formatter only needs `{raw_*_data}` + `{triage:classification}` from state — not the fetcher's conversation. See `_clear_history` callbacks in both existing agents. ADK discussion #3457.

### 11.3 ADK callback mechanics

9. **Never rename `callback_context` / `tool_context` / `llm_request` / `llm_response` params.** ADK binds by name. Rename breaks the callback silently. Use `# noqa: ARG001` to appease ruff instead of renaming.
10. **`ToolContext` must be a runtime import inside tool function bodies, not `TYPE_CHECKING`.** (`feedback_adk_callback_naming` memory)
11. **Never raise from a callback.** Kills the run. Log + set state flag + return sentinel Content.
12. **`before_agent_callback` returning Content only skips that one agent** — SequentialAgent still advances. Rule B propagates via `triage:skip_impact` sentinel.
13. ✨ **`event.author` is `None` on the first user turn.** Coalesce when emitting SSE `agent_started`. Seen in [adk-python#4244](https://github.com/google/adk-python/issues/4244).
14. ✨ **SequentialAgent early-response bug.** [adk-python#1770](https://github.com/google/adk-python/issues/1770) — intermediate sub-agents with `output_key` occasionally emit `is_final_response()` prematurely. Mitigation: our Classifier and Impact both use the two-agent fetcher+formatter pattern; the formatter's `include_contents="none"` + `before_model_callback=_clear_history` reduces this. If we see it, filter on `author != "classifier_formatter"` when counting completion.

### 11.4 State + sessions

15. **Never mutate `session.state` directly.** Use `callback_context.state[...]`. (`.claude/rules/agents.md` §3)
16. **State values must be JSON-serialisable.** Pydantic models → `.model_dump_json()` first. ADK dumps JSON strings into state for `output_schema` writes — readers must `json.loads`.
17. **`temp:*` keys survive the sequential pipeline** (same InvocationContext), but disappear after the runner's outer turn completes.
18. ✨ **`InMemorySessionService.create_session(state=...)` seeds initial state cleanly.** Use this to seed `triage:event_id` before `runner.run_async`.

### 11.5 Gemini / `thinking_budget`

19. **`thinking_budget=0` degrades classification on Flash.** Hit in Sprint 1 — Classifier produces shallow output. Default to `1024` for classifier/impact, `0` only for the Tier 2 Judge. (`.claude/rules/agents.md` §8)
20. **Safety thresholds block logistics terms** ("strike", "hazard cargo"). Loosen to `BLOCK_ONLY_HIGH`. (`.claude/rules/agents.md` §9)

### 11.6 FastAPI + SSE

21. **Three headers required on Cloud Run SSE**: `Cache-Control: no-cache`, `X-Accel-Buffering: no`, `Connection: keep-alive`. Without them Cloud Run buffers the whole stream. (`docs/research/zettel-fastapi-sse-cloud-run.md`)
22. **15s keepalive (`: ping\n\n`) prevents idle-timeout drop.** Emit from an asyncio task that races with the event generator.
23. ✨ **Don't put Cloud Run SSE behind API Gateway.** API Gateway buffers. Direct Cloud Run URL only for the streaming endpoint.
24. ✨ **Never raise out of an SSE async generator.** FastAPI renders the exception page as `text/event-stream` body; EventSource hangs. Wrap in try/except and yield a terminal error frame.

### 11.7 Environment + config

25. **`.env` must have all `Settings` fields** or `adk web` fails to start (memory: `feedback_env_emulator_settings`).
26. **Firestore queries: `FieldFilter(...)` not tuple syntax.** (memory: same)
27. **`FIREBASE_AUTH_EMULATOR_HOST` in Cloud Run prod env is a live exploit.** Admin SDK accepts forged tokens. Pydantic-settings validator rejects when `ENV != "dev"`. (`.claude/rules/security.md` §12)

### 11.8 Cross-cutting

28. ✨ **Factory functions, not module-level `root_agent` for multi-agent composition.** `SequentialAgent(sub_agents=[classifier, impact])` — if `classifier` is a module-level `root_agent` that's already been embedded in another `SequentialAgent`, ADK raises "agent already has parent." Always call `create_classifier()` / `create_impact()` inside `create_triage_pipeline()`. (existing pattern in both agent modules)

---

## 12. A2A-forward compatibility

Our architecture commits to **A2A-first**: any agent must be exposable via Google's Agent-to-Agent protocol without a rewrite (CLAUDE.md, memory: `project_architecture_a2a_vendor_free`).

**What `SequentialAgent` gives us for free:**
- It subclasses `BaseAgent`, so it can be wrapped by `A2aAgentExecutor` and surfaced via `AgentCardBuilder` exactly like any other agent.
- Its `description=` field becomes the Agent Card description.
- Its `name=` becomes the Agent Card name.
- Input/output schemas surface via the sub-agent schemas (no extra work on our side).

**What a bare Python router would lose:**
- `AgentCardBuilder` needs an agent to introspect. A function isn't one.
- We'd have to hand-write `agent.json` and the `A2AFastAPIApplication` mount — explicitly banned (`.claude/rules/agents.md` §11).

**What a `BaseAgent` subclass (custom agent) would lose vs `SequentialAgent`:**
- A `BaseAgent` subclass works for A2A, but requires us to own `_run_async_impl`. Which means the A2A executor has to serialize our custom logic correctly — more risk, more testing.

**Tier-3 flip:** when we add A2A, the work is `uvx agent-starter-pack create ... --agent adk_a2a`, then lift the scaffolded `A2aAgentExecutor` and `AgentCardBuilder` into `runners/`. The pipeline agent itself doesn't change.

---

## 13. Testing strategy

Reference: `.claude/rules/testing.md` (the full rule file), `.claude/rules/new-feature-checklist.md` §A step 8.

### 13.1 Unit — pure callbacks

`tests/unit/agents/triage/test_pipeline_callbacks.py`:

```python
from unittest.mock import MagicMock

from supply_chain_triage.modules.triage.agents.pipeline import (
    _rule_b_safety_check,
    _rule_cf_impact_gate,
)


class FakeCallbackContext:
    def __init__(self, state: dict) -> None:
        self.state = state
        self.agent_name = "test"
        self.invocation_id = "inv_test"
        self.user_content = None


def test_rule_b_hits_on_english_keyword() -> None:
    ctx = FakeCallbackContext(state={
        "triage:event_raw_text": "Driver was hospitalized after the tanker explosion.",
    })
    result = _rule_b_safety_check(ctx)
    assert result is not None
    assert ctx.state["triage:status"] == "escalated_to_human_safety"
    assert ctx.state["triage:skip_impact"] is True
    assert "hospitalized" in ctx.state["triage:safety_match"]
    assert "tanker explosion" in ctx.state["triage:safety_match"]


def test_rule_b_hits_on_hinglish_keyword() -> None:
    ctx = FakeCallbackContext(state={
        "triage:event_raw_text": "Durghatna ho gayi hai highway pe, driver ko chot lagi.",
    })
    result = _rule_b_safety_check(ctx)
    assert result is not None
    assert {"durghatna", "chot"}.issubset(set(ctx.state["triage:safety_match"]))


def test_rule_b_nfkc_normalizes_fullwidth() -> None:
    ctx = FakeCallbackContext(state={
        "triage:event_raw_text": "There was a ﬁre at hub",  # fi ligature
    })
    result = _rule_b_safety_check(ctx)
    assert result is not None
    assert "fire" in ctx.state["triage:safety_match"]


def test_rule_b_misses_clean_text() -> None:
    ctx = FakeCallbackContext(state={
        "triage:event_raw_text": "Truck is delayed by 3 hours due to traffic.",
    })
    assert _rule_b_safety_check(ctx) is None
    assert "triage:safety_match" not in ctx.state


def test_rule_c_overrides_rule_f_for_regulatory() -> None:
    ctx = FakeCallbackContext(state={
        "triage:classification": '{"exception_type":"regulatory_compliance","severity":"LOW","confidence":0.9}',
    })
    assert _rule_cf_impact_gate(ctx) is None  # proceed — Impact runs
    assert ctx.state.get("triage:rule_c_applied") is True


def test_rule_f_skips_low_severity_when_not_regulatory() -> None:
    ctx = FakeCallbackContext(state={
        "triage:classification": '{"exception_type":"carrier_capacity_failure","severity":"LOW","confidence":0.9}',
    })
    result = _rule_cf_impact_gate(ctx)
    assert result is not None
    assert ctx.state["triage:skip_impact"] is True
    assert ctx.state["triage:status"] == "complete"
    assert ctx.state.get("triage:rule_f_applied") is True


def test_rule_b_sentinel_takes_priority_over_c_and_f() -> None:
    ctx = FakeCallbackContext(state={
        "triage:skip_impact": True,
        "triage:classification": '{"exception_type":"regulatory_compliance","severity":"LOW"}',
    })
    result = _rule_cf_impact_gate(ctx)
    assert result is not None
    assert ctx.state.get("triage:rule_c_applied") is not True
```

### 13.2 Unit — TriageResult assembly

`tests/unit/runners/test_triage_assembly.py`:

```python
def test_assemble_complete_with_both_agents(...) -> None: ...
def test_assemble_rule_f_impact_none_status_complete(...) -> None: ...
def test_assemble_rule_b_status_escalated_safety(...) -> None: ...
def test_assemble_impact_failure_status_partial_with_errors(...) -> None: ...
def test_assemble_missing_classification_status_partial(...) -> None: ...
```

### 13.3 Integration — full pipeline against emulators

`tests/integration/triage/test_pipeline_end_to_end.py`:

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_pipeline_happy_path(firestore_emulator, seed_sample_event):
    # Seed an exception_event doc
    # Invoke create_triage_pipeline() via a Runner
    # Assert final session.state has triage:classification + triage:impact
    # Assert no errors in state

@pytest.mark.integration
@pytest.mark.asyncio
async def test_pipeline_rule_b_short_circuits(firestore_emulator):
    # Seed an event with "tanker explosion" in description
    # Run pipeline
    # Assert triage:status == "escalated_to_human_safety"
    # Assert no Impact run — no triage:impact key

@pytest.mark.integration
@pytest.mark.asyncio
async def test_pipeline_rule_f_skips_impact(firestore_emulator):
    # Seed a LOW-severity non-regulatory event
    # Run pipeline
    # Assert triage:classification present
    # Assert triage:impact absent
    # Assert triage:status == "complete"

@pytest.mark.integration
@pytest.mark.asyncio
async def test_pipeline_rule_c_forces_impact_on_low(firestore_emulator):
    # Seed a LOW-severity regulatory event
    # Assert triage:impact present despite LOW severity
```

### 13.4 FastAPI SSE endpoint test

`tests/integration/runners/test_triage_sse.py`:

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_sse_emits_all_four_event_types(client):
    async with client.stream("POST", "/api/v1/triage/stream", json={"event_id": "..."}) as resp:
        events = [chunk async for chunk in resp.aiter_lines()]
    event_types = {e for e in events if e.startswith("event:")}
    assert "event: agent_started" in event_types
    assert "event: tool_invoked" in event_types
    assert "event: partial_result" in event_types
    assert "event: agent_completed" in event_types
    assert "event: triage_result" in event_types
```

### 13.5 Coverage

Callbacks are pure Python — target **95%+ branch coverage** via unit tests (deterministic, no LLM). Integration tests cover the wiring, not the invariants.

### 13.6 Evalsets

`evals/` has per-agent evalsets but **not** a coordinator/pipeline evalset — [adk-python#3434](https://github.com/google/adk-python/issues/3434) precludes evaluating SequentialAgent cleanly today. Add a pipeline-level evalset when that bug closes. For Tier 1, Classifier and Impact evalsets stand alone.

---

## 14. File-by-file build list

Everything to create or modify in the Coordinator sprint. Line counts are rough ceilings from `.claude/rules/code-quality.md` §1.

### New files

| Path | LOC | Purpose |
|---|---|---|
| `src/supply_chain_triage/modules/triage/agents/pipeline.py` | ~120 | `create_triage_pipeline()` factory — wires `SequentialAgent(classifier, impact)` with pipeline-level `before_agent_callback` (seed raw text) and `after_agent_callback` (duration log). |
| `src/supply_chain_triage/modules/triage/agents/callbacks.py` | ~150 | Pure-Python callback module: `_rule_b_safety_check`, `_rule_cf_impact_gate`, `_seed_event_raw_text`, helpers. Importable + unit-testable in isolation. |
| `src/supply_chain_triage/modules/triage/agents/_constants.py` | ~40 | Safety keyword set, placeholder classification template, priority labels. |
| `src/supply_chain_triage/runners/triage_runner.py` | ~180 | FastAPI app with `/api/v1/triage` (blocking) + `/api/v1/triage/stream` (SSE) + `/health`. |
| `src/supply_chain_triage/runners/_triage_stream.py` | ~150 | `_triage_event_stream` async generator + SSE frame helpers + keepalive task. |
| `src/supply_chain_triage/runners/_triage_assembly.py` | ~100 | `_assemble_triage_result`, `_load_classification`, `_load_impact`, `_build_summary`, `_build_trace`. |
| `src/supply_chain_triage/modules/triage/memory/exception_events.py` | ~80 | `get_exception_event_raw_text(event_id) -> str \| None` — Firestore read used by pipeline's `before_agent_callback`. |
| `tests/unit/agents/triage/test_pipeline_callbacks.py` | ~200 | All Rule B/C/F unit tests + priority-ordering tests. |
| `tests/unit/runners/test_triage_assembly.py` | ~150 | TriageResult assembly tests. |
| `tests/integration/triage/test_pipeline_end_to_end.py` | ~200 | Happy path + 3 rule scenarios against Firestore emulator. |
| `tests/integration/runners/test_triage_sse.py` | ~120 | SSE event-type presence + ordering. |

### Modified files

| Path | Change |
|---|---|
| `src/supply_chain_triage/modules/triage/agents/__init__.py` | Export `create_triage_pipeline`. |
| `src/supply_chain_triage/modules/triage/agents/classifier/agent.py` | **No change.** Rule B's callback is attached at pipeline level, not here. |
| `src/supply_chain_triage/modules/triage/agents/impact/agent.py` | Add parameter `before_agent_callback=_rule_cf_impact_gate` to the `SequentialAgent` return in `create_impact()` — this is where Rules C and F apply. |
| `src/supply_chain_triage/modules/triage/models/triage_result.py` | **No change** — already supports `impact: ImpactResult \| None`. |
| `pyproject.toml` | Confirm `tenacity>=8.0` in runtime deps. Already likely present; no-op if so. |
| `docs/sessions/2026-04-18-coordinator-research.md` | Session note with decisions + this doc pointer. |

### Wiring order (suggested)

1. `_constants.py` + `callbacks.py` (pure, unit-testable, no ADK deps needed in callbacks.py beyond type hints).
2. Unit tests for callbacks.
3. `memory/exception_events.py`.
4. `pipeline.py`.
5. `adk web src/supply_chain_triage/modules/triage/agents` smoke test against seeded emulator events.
6. `_triage_assembly.py` + its unit tests.
7. `_triage_stream.py`.
8. `triage_runner.py`.
9. Integration tests.

---

## 15. Full code skeletons (ready to paste)

Cut-and-paste scaffolds. Minor polish (imports ordering, logger naming) expected.

### 15.1 `agents/_constants.py`

```python
"""Module-level constants for the triage pipeline callbacks.

Split from pipeline.py to keep callback logic pure and the agent file small.
"""

from __future__ import annotations

from supply_chain_triage.modules.triage.models.common_types import Severity

# Rule B — safety keyword allow-list.
# English + Hindi-transliterated (Hinglish). Native Devanagari deferred to Tier 2.
SAFETY_KEYWORDS: frozenset[str] = frozenset(
    {
        # English
        "accident",
        "injury",
        "injured",
        "death",
        "killed",
        "fatality",
        "fire",
        "spill",
        "hazmat",
        "hazardous",
        "medical emergency",
        "collapsed",
        "hospitalized",
        "chemical leak",
        "tanker explosion",
        "overturned",
        # Hinglish (transliterated Hindi)
        "durghatna",        # accident
        "chot",             # injury
        "maut",             # death
        "marne",            # dying
        "aag",              # fire
        "jaan ka khatra",   # life-threatening
        "hospital",         # same spelling
        "bimari",           # illness
        "zakhmi",           # wounded
        "khatarnak",        # dangerous
    }
)

# Placeholder ClassificationResult written when Rule B short-circuits Classifier.
# Downstream readers (Impact callback, runner assembly) expect this key to exist.
SAFETY_PLACEHOLDER_CLASSIFICATION: dict[str, object] = {
    "exception_type": "safety_incident",
    "severity": Severity.CRITICAL.value,
    "confidence": 1.0,
    "requires_human_approval": True,
    "key_facts": ["safety_keyword_match"],
}

REGULATORY_EXCEPTION_TYPE = "regulatory_compliance"
```

### 15.2 `agents/callbacks.py`

```python
"""Pure callback logic for the triage pipeline — Rules B, C, F.

Callbacks are unit-testable in isolation. No ADK imports in the runtime code path
beyond ``google.genai.types.Content`` for short-circuit returns (which is the
ADK-expected contract, not an orchestration import).
"""

from __future__ import annotations

import json
import unicodedata
from typing import TYPE_CHECKING, Any

from google.genai import types as genai_types

from supply_chain_triage.modules.triage.agents._constants import (
    REGULATORY_EXCEPTION_TYPE,
    SAFETY_KEYWORDS,
    SAFETY_PLACEHOLDER_CLASSIFICATION,
)
from supply_chain_triage.modules.triage.models.common_types import (
    EscalationPriority,
    Severity,
    TriageStatus,
)
from supply_chain_triage.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import MutableMapping

    from google.adk.agents.callback_context import CallbackContext

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Pipeline-level: seed raw event text from Firestore (runs first, once).
# ---------------------------------------------------------------------------


async def seed_event_raw_text(callback_context: CallbackContext) -> None:
    """Populate ``triage:event_raw_text`` from Firestore before Classifier runs.

    Called as the pipeline's own ``before_agent_callback``. Keeps the runner
    thin — the pipeline fetches its own context.
    """
    from supply_chain_triage.modules.triage.memory.exception_events import (
        get_exception_event_raw_text,
    )

    event_id = callback_context.state.get("triage:event_id")
    if not event_id:
        logger.warning("seed_event_raw_text_no_event_id")
        return
    raw = await get_exception_event_raw_text(event_id)
    if raw:
        callback_context.state["triage:event_raw_text"] = raw


# ---------------------------------------------------------------------------
# Rule B — safety keyword scan, runs before Classifier.
# ---------------------------------------------------------------------------


def rule_b_safety_check(callback_context: CallbackContext) -> genai_types.Content | None:
    """Scan the raw event text for safety keywords; short-circuit on hit."""
    raw = callback_context.state.get("triage:event_raw_text", "")
    if not isinstance(raw, str) or not raw:
        return None

    normalized = unicodedata.normalize("NFKC", raw).casefold()
    matched = sorted(kw for kw in SAFETY_KEYWORDS if kw in normalized)
    if not matched:
        return None

    _write_safety_escalation(callback_context.state, matched)
    logger.warning("rule_b_safety_escalation", matched=matched)
    return genai_types.Content(
        role="model",
        parts=[
            genai_types.Part(
                text=f"Safety-keyword escalation. Matched: {', '.join(matched)}.",
            )
        ],
    )


def _write_safety_escalation(
    state: MutableMapping[str, Any], matched: list[str]
) -> None:
    state["triage:status"] = TriageStatus.escalated_to_human_safety.value
    state["triage:skip_impact"] = True
    state["triage:safety_match"] = matched
    state["triage:escalation_priority"] = EscalationPriority.safety.value
    state["triage:rule_b_applied"] = True

    placeholder = dict(SAFETY_PLACEHOLDER_CLASSIFICATION)
    placeholder["safety_escalation"] = {
        "trigger_type": "keyword_detection",
        "matched_terms": matched,
        "escalation_reason": "Rule B short-circuit — safety keyword in raw event text",
    }
    state["triage:classification"] = json.dumps(placeholder)


# ---------------------------------------------------------------------------
# Rules C + F — run before Impact. Priority: B sentinel > C > F.
# ---------------------------------------------------------------------------


def rule_cf_impact_gate(callback_context: CallbackContext) -> genai_types.Content | None:
    """Gate Impact execution. Returns Content to skip; None to proceed."""
    state = callback_context.state

    # Rule B sentinel — upstream safety escalation. Hard skip.
    if state.get("triage:skip_impact"):
        return _skip_content("Impact skipped — Rule B upstream safety escalation.")

    classification = _parse_classification(state)
    if classification is None:
        # Classifier produced no parseable output. Let Impact try — better to
        # have partial information than skip entirely.
        logger.warning("rule_cf_no_classification_proceed")
        return None

    # Rule C — regulatory always runs Impact, regardless of severity.
    if classification.get("exception_type") == REGULATORY_EXCEPTION_TYPE:
        state["triage:rule_c_applied"] = True
        state["triage:escalation_priority"] = EscalationPriority.regulatory.value
        logger.info("rule_c_applied", severity=classification.get("severity"))
        return None

    # Rule F — LOW severity + non-regulatory → skip.
    if classification.get("severity") == Severity.LOW.value:
        state["triage:skip_impact"] = True
        state["triage:status"] = TriageStatus.complete.value
        state["triage:rule_f_applied"] = True
        logger.info("rule_f_applied")
        return _skip_content("LOW severity — Impact assessment skipped per Rule F.")

    return None


def _parse_classification(state: MutableMapping[str, Any]) -> dict[str, Any] | None:
    raw = state.get("triage:classification")
    if not isinstance(raw, str):
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _skip_content(message: str) -> genai_types.Content:
    return genai_types.Content(
        role="model",
        parts=[genai_types.Part(text=message)],
    )
```

### 15.3 `agents/pipeline.py`

```python
"""Triage pipeline — SequentialAgent(Classifier, Impact) with rule callbacks.

Entry point for the Tier 1 triage flow. Rule B fires in the pipeline's own
``before_agent_callback`` (safety keywords short-circuit Classifier). Rules C
and F fire in the Impact sub-agent's ``before_agent_callback`` (injected
here, not in ``impact/agent.py``, so the rule surface stays co-located).

Factory pattern per ADK cheatsheet guidance — avoids "agent already has parent"
errors when composing sub-agents.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from google.adk.agents import SequentialAgent

from supply_chain_triage.modules.triage.agents.callbacks import (
    rule_b_safety_check,
    rule_cf_impact_gate,
    seed_event_raw_text,
)
from supply_chain_triage.modules.triage.agents.classifier.agent import create_classifier
from supply_chain_triage.modules.triage.agents.impact.agent import create_impact
from supply_chain_triage.utils.logging import get_logger, log_agent_invocation

if TYPE_CHECKING:
    from google.adk.agents.callback_context import CallbackContext

logger = get_logger(__name__)

_AGENT_NAME = "triage_pipeline"
_STATE_START = f"temp:{_AGENT_NAME}:start_perf_ns"


def _before_pipeline(callback_context: CallbackContext) -> None:
    callback_context.state[_STATE_START] = time.perf_counter_ns()


async def _before_pipeline_async(callback_context: CallbackContext) -> None:
    """Combined: stamp timer + seed raw event text from Firestore."""
    callback_context.state[_STATE_START] = time.perf_counter_ns()
    await seed_event_raw_text(callback_context)


def _after_pipeline(callback_context: CallbackContext) -> None:
    start_ns = callback_context.state.get(_STATE_START)
    duration_ms = (
        (time.perf_counter_ns() - start_ns) / 1_000_000 if start_ns is not None else 0.0
    )
    log_agent_invocation(
        agent_name=_AGENT_NAME,
        duration_ms=duration_ms,
    )


def create_triage_pipeline() -> SequentialAgent:
    """Create the triage pipeline.

    Wires Classifier + Impact into a deterministic sequence. Attaches the
    rule callbacks at the sub-agent level so each rule lives with the agent
    it gates.
    """
    classifier = create_classifier()
    # Inject Rule B callback on the Classifier sub-agent.
    # SequentialAgent supports before_agent_callback; stacking on top of the
    # existing _before_agent (timer) works because ADK allows a list of
    # callbacks via the same slot — or we wrap:
    _inject_before_agent_callback(classifier, rule_b_safety_check)

    impact = create_impact()
    _inject_before_agent_callback(impact, rule_cf_impact_gate)

    return SequentialAgent(
        name=_AGENT_NAME,
        description=(
            "Triage pipeline — Classifier then Impact. Deterministic rules "
            "(safety override, regulatory auto-escalate, LOW-severity skip) "
            "execute via before_agent_callback on each sub-agent."
        ),
        sub_agents=[classifier, impact],
        before_agent_callback=_before_pipeline_async,
        after_agent_callback=_after_pipeline,
    )


def _inject_before_agent_callback(agent, new_cb) -> None:  # noqa: ANN001 — ADK BaseAgent
    """Prepend a callback to an agent's before_agent_callback slot.

    ADK's slot accepts a single callable or a list. We wrap the existing one
    (if present) so both run in order: new_cb first, then the existing
    timer/init callback. If new_cb returns Content, the existing one still
    runs? No — ADK short-circuits on the first non-None return in list form.
    See: https://adk.dev/callbacks/types-of-callbacks/
    """
    existing = getattr(agent, "before_agent_callback", None)
    if existing is None:
        agent.before_agent_callback = new_cb
    elif callable(existing):
        agent.before_agent_callback = [new_cb, existing]
    elif isinstance(existing, list):
        agent.before_agent_callback = [new_cb, *existing]
    else:
        agent.before_agent_callback = new_cb


# ADK discovery — `adk web` looks for `root_agent` at module level.
root_agent = create_triage_pipeline()
```

**Note on the callback injection helper.** If ADK's current version does not accept a list for `before_agent_callback` on the target agent type (verify during build — see [Types of callbacks](https://adk.dev/callbacks/types-of-callbacks/) for the authoritative list-vs-single contract in your pinned version), fall back to a wrapper that calls both in order:

```python
def _combine(first, second):
    def _wrapped(ctx):
        result = first(ctx)
        if result is not None:
            return result
        return second(ctx) if second else None
    return _wrapped
```

Either pattern is fine; prefer the list form if supported.

### 15.4 `runners/triage_runner.py`

See §10.1 above for the full shape. Key entry points:

```python
@app.post("/api/v1/triage", response_model=TriageResult)
async def triage_blocking(*, payload: TriageInput) -> TriageResult: ...

@app.post("/api/v1/triage/stream")
async def triage_streaming(*, payload: TriageInput) -> StreamingResponse: ...
```

### 15.5 `runners/_triage_stream.py`

See §9.5 above for the full `_triage_event_stream` async generator. Plus a keepalive task:

```python
import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

_KEEPALIVE_INTERVAL_S = 15.0


@asynccontextmanager
async def _with_keepalive(queue: asyncio.Queue[str]):
    """Push SSE keepalive comments into the outbound queue every 15s."""

    async def _ping() -> None:
        try:
            while True:
                await asyncio.sleep(_KEEPALIVE_INTERVAL_S)
                await queue.put(": ping\n\n")
        except asyncio.CancelledError:
            return

    task = asyncio.create_task(_ping())
    try:
        yield
    finally:
        task.cancel()
```

### 15.6 `runners/_triage_assembly.py`

```python
"""Build a TriageResult from the session state left by the pipeline."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from supply_chain_triage.modules.triage.models.classification import ClassificationResult
from supply_chain_triage.modules.triage.models.common_types import (
    EscalationPriority,
    TriageStatus,
)
from supply_chain_triage.modules.triage.models.impact import ImpactResult
from supply_chain_triage.modules.triage.models.triage_result import TriageResult


def assemble_triage_result(
    *,
    event_id: str,
    state: Mapping[str, Any],
    duration_ms: int,
    errors: list[str],
) -> TriageResult:
    """Build a TriageResult from the final session state + runner-collected errors."""
    classification = _load_classification(state)
    impact = _load_impact(state)
    status = _resolve_status(state, classification, impact, errors)
    summary = _build_summary(classification, impact, status, errors)
    escalation = _load_escalation_priority(state)
    trace = _build_trace(state)

    return TriageResult(
        event_id=event_id,
        status=status,
        classification=classification,
        impact=impact,
        summary=summary,
        processing_time_ms=duration_ms,
        errors=errors,
        escalation_priority=escalation,
        coordinator_trace=trace,
    )


def _load_classification(state: Mapping[str, Any]) -> ClassificationResult | None:
    raw = state.get("triage:classification")
    if not isinstance(raw, str):
        return None
    try:
        return ClassificationResult.model_validate_json(raw)
    except ValidationError:
        return None


def _load_impact(state: Mapping[str, Any]) -> ImpactResult | None:
    raw = state.get("triage:impact")
    if not isinstance(raw, str):
        return None
    try:
        return ImpactResult.model_validate_json(raw)
    except ValidationError:
        return None


def _resolve_status(
    state: Mapping[str, Any],
    classification: ClassificationResult | None,
    impact: ImpactResult | None,
    errors: list[str],
) -> TriageStatus:
    # Hard-state wins — Rule B wrote escalated_to_human_safety already.
    raw_status = state.get("triage:status")
    if raw_status == TriageStatus.escalated_to_human_safety.value:
        return TriageStatus.escalated_to_human_safety

    # Errors → partial (except when caused by Rule F which is expected).
    if errors:
        return TriageStatus.partial

    # Low-confidence Classifier sets requires_human_approval.
    if classification and classification.requires_human_approval:
        return TriageStatus.escalated_to_human

    # Impact failed silently (no errors, but runner retry gave up).
    if raw_status == TriageStatus.partial.value:
        return TriageStatus.partial

    return TriageStatus.complete


def _load_escalation_priority(state: Mapping[str, Any]) -> EscalationPriority | None:
    raw = state.get("triage:escalation_priority")
    if not raw:
        return None
    try:
        return EscalationPriority(raw)
    except ValueError:
        return None


def _build_trace(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    trace: list[dict[str, Any]] = []
    for rule_key, label in (
        ("triage:rule_b_applied", "B"),
        ("triage:rule_c_applied", "C"),
        ("triage:rule_f_applied", "F"),
    ):
        if state.get(rule_key):
            trace.append({"rule": label, "applied": True})
    if matched := state.get("triage:safety_match"):
        trace.append({"safety_match": matched})
    return trace


def _build_summary(
    classification: ClassificationResult | None,
    impact: ImpactResult | None,
    status: TriageStatus,
    errors: list[str],
) -> str:
    if status == TriageStatus.escalated_to_human_safety:
        return "Safety escalation — Impact skipped, human review required."
    if errors and classification and not impact:
        return f"Partial — classification {classification.severity}, impact unavailable."
    if classification and not impact:
        return f"{classification.severity} {classification.exception_type} — Impact skipped (Rule F)."
    if classification and impact:
        return (
            f"{classification.severity} {classification.exception_type} "
            f"— {impact.overall_severity} impact across "
            f"{len(impact.affected_shipments)} shipments."
        )
    return "Triage incomplete."
```

### 15.7 `modules/triage/memory/exception_events.py`

```python
"""Memory adapter: raw exception event text for Rule B keyword scan."""

from __future__ import annotations

from supply_chain_triage.core.config import get_firestore_client


async def get_exception_event_raw_text(event_id: str) -> str | None:
    """Return the concatenated raw text of an exception event (or None if absent).

    Rule B scans this string for safety keywords. Concatenates description +
    any free-text transcription fields. Pure Firestore read, no ADK imports.
    """
    db = get_firestore_client()
    doc = await db.collection("exception_events").document(event_id).get()
    if not doc.exists:
        return None
    data = doc.to_dict() or {}
    parts: list[str] = []
    for key in ("description", "transcript", "original_text", "english_translation"):
        value = data.get(key)
        if isinstance(value, str) and value:
            parts.append(value)
    return "\n".join(parts) if parts else None
```

---

## 16. What we explicitly deferred

- **Rules A, D, E** — need Supermemory-backed user context. Tier 2 work.
- **Devanagari Hindi safety keywords** (not just transliterated). Needs Unicode tokenization, not substring. Tier 2.
- **A2A surface for the pipeline.** Framework in place; wiring is Tier 3.
- **Pipeline-level evalset.** Blocked on [adk-python#3434](https://github.com/google/adk-python/issues/3434).
- **Cloud Run deploy.** Per `.claude/rules/deployment.md` — not part of this build; validate locally first.
- **`AgentRunner` protocol shim fill-out** (`runners/agent_runner.py`). Sprint 3 work — triage runner stays ADK-coupled in Tier 1; the shim collapses them once we ship more modules.

---

## 17. Sources

### Authoritative ADK documentation

- [Multi-agent systems (ADK)](https://adk.dev/agents/multi-agents/)
- [Sequential agents (ADK)](https://adk.dev/agents/workflow-agents/sequential-agents/)
- [Types of callbacks (ADK)](https://adk.dev/callbacks/types-of-callbacks/)
- [Callback design patterns (ADK)](https://adk.dev/callbacks/design-patterns-and-best-practices/)
- [Session state (ADK)](https://adk.dev/sessions/state/)
- [Events (ADK)](https://adk.dev/events/)
- [Agent runtime (ADK)](https://adk.dev/runtime/)
- [Instructions and prompts (DeepWiki ADK)](https://deepwiki.com/google/adk-python/3.7-instructions-and-prompts)

### GitHub discussions + issues

- [adk-python#2290 — Halting SequentialAgent mid-chain via custom BaseAgent](https://github.com/google/adk-python/discussions/2290)
- [adk-python#3392 — Runtime logic for excluding a subagent](https://github.com/google/adk-python/discussions/3392)
- [adk-python#3778 — ConditionalAgent / BranchAgent / DynamicSubAgentSet feature request](https://github.com/google/adk-python/discussions/3778)
- [adk-python#1770 — SequentialAgent sub-agent prematurely emits final_response](https://github.com/google/adk-python/issues/1770)
- [adk-python#147 — Multi-agent architecture: sub-agent doesn't return to root](https://github.com/google/adk-python/issues/147)
- [adk-python#2797 — before_agent_callback bug](https://github.com/google/adk-python/issues/2797)
- [adk-python#4244 — run_sse does not propagate exceptions](https://github.com/google/adk-python/issues/4244)
- [adk-python#3434 — Evalset issue for coordinator agents](https://github.com/google/adk-python/issues/3434)
- [adk-python#3258 — UI integration guide (SSE + FastAPI)](https://github.com/google/adk-python/discussions/3258)
- [adk-python#3457 — include_contents="none" history clearing](https://github.com/google/adk-python/discussions/3457)

### Supporting references

- [Build multi-agent systems with ADK (Google Cloud blog)](https://cloud.google.com/blog/products/ai-machine-learning/build-multi-agentic-systems-using-google-adk)
- [Developer's guide to multi-agent patterns in ADK (Google Developers Blog)](https://developers.googleblog.com/developers-guide-to-multi-agent-patterns-in-adk/)
- [ADK tutorial: streaming and SSE (community)](https://raphaelmansuy.github.io/adk_training/docs/streaming_sse/)
- [Mete Atamel — Quick Guide to ADK Callbacks](https://atamel.dev/posts/2025/11-03_quick_guide_adk_callbacks/)
- [Arjun Prabhulal — ADK Callbacks deep dive](https://arjunprabhulal.com/adk-callbacks/)
- [minherz — Master ADK Callbacks: DOs and DON'Ts](https://leoy.blog/posts/master-adk-callbacks/)
- [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [FastAPI StreamingResponse on Cloud Run — Google Discuss thread](https://discuss.google.dev/t/fastapi-streamingresponse-on-cloud-run/182021)
- [MDN — Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)

### In-repo references (don't duplicate; read alongside)

- `docs/research/Supply-Chain-Agent-Spec-Coordinator.md` — original Rule A-F specification.
- `docs/research/adk-best-practices.md` — general ADK patterns.
- `docs/research/gemini-structured-output-gotchas.md` — structured-output landmines. Canonical. **Read before writing any `output_schema`.**
- `docs/research/zettel-fastapi-sse-cloud-run.md` — header trio + keepalive story.
- `docs/research/zettel-adk-before-model-callback.md` — callback hook semantics; complements this doc.
- `src/supply_chain_triage/modules/triage/agents/classifier/agent.py` — existing two-agent pattern.
- `src/supply_chain_triage/modules/triage/agents/impact/agent.py` — existing pattern + template placeholder usage.
- `src/supply_chain_triage/modules/triage/models/triage_result.py` — already supports `impact=None`, `status=escalated_to_human_safety`.
- `src/supply_chain_triage/runners/classifier_runner.py` / `impact_runner.py` / `_shared.py` — runner templates.
- `.claude/rules/agents.md`, `.claude/rules/imports.md`, `.claude/rules/placement.md`, `.claude/rules/architecture-layers.md`, `.claude/rules/api-routes.md`, `.claude/rules/models.md`, `.claude/rules/security.md`, `.claude/rules/logging.md`, `.claude/rules/guardrails.md`, `.claude/rules/new-feature-checklist.md`, `.claude/rules/observability.md`, `.claude/rules/code-quality.md` — project rules touched by this work.

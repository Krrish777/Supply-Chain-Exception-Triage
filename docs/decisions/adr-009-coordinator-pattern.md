---
title: "ADR-009 — Coordinator as SequentialAgent + before_agent_callback (no LlmAgent coordinator)"
type: adr
adr_number: 009
status: accepted
decided_on: 2026-04-18
decided_by: user + research-session
last_updated: 2026-04-18
supersedes: "Sprint 3 PRD v1 (LlmAgent + sub_agents + transfer_to_agent design)"
---

# ADR-009 — Coordinator pattern: SequentialAgent + `before_agent_callback`

## Status

Accepted (pending implementation in Sprint 3 build session).

## Context

Tier 1 requires a pipeline that runs Classifier, then (conditionally) Impact, applying three delegation rules:

- **Rule B** — safety keyword in raw text → short-circuit to `escalated_to_human_safety`, skip both specialists.
- **Rule C** — regulatory_compliance classification → force Impact even if severity is LOW.
- **Rule F** — LOW severity non-regulatory → skip Impact.

Rules A, D, E (WhatsApp urgency, festival/monsoon context, D2C reputation) require a memory layer and are deferred to Tier 2. Only B/C/F are in scope for Tier 1.

Three candidate patterns were considered:

1. **`LlmAgent` Coordinator with `sub_agents` + `transfer_to_agent` AutoFlow** — the original Sprint 3 PRD v1 choice. LLM reads sub-agent descriptions and picks delegation.
2. **`SequentialAgent(classifier, impact)` with `before_agent_callback` on each** — workflow agent + deterministic callbacks that short-circuit or skip.
3. **`CustomAgent` (`BaseAgent` subclass)** — hand-rolled `_run_async_impl` orchestrator.
4. **Bare Python router in `runners/`** — not really an "agent" at all; procedural orchestration.

## Decision

**Choose option 2: `SequentialAgent(classifier, impact)` with `before_agent_callback` on each sub-agent.**

- Classifier's callback checks raw text against a 26-keyword safety list (16 English + 10 Hindi-transliterated, NFKC + casefold normalized). On match, returns an escalation `Content` frame + writes `triage:skip_impact=True` to session state → pipeline short-circuits.
- Impact's callback reads `triage:classification` + `triage:skip_impact`. Rule C overrides Rule F; if skipping, returns a skip `Content` marker that becomes `impact=None` in the final assembled `TriageResult`.
- Conflict resolution order (B > C > F) is encoded in a single `if/elif/else` ladder in the Impact callback — no boolean-combination bugs.
- A thin `runners/triage_runner.py` assembles the final `TriageResult` from session state and handles SSE event emission.

## Rationale

| Criterion | LlmAgent+sub_agents | SequentialAgent+callbacks (chosen) | CustomAgent | Bare router |
|---|---|---|---|---|
| Deterministic for known rules | ❌ LLM picks | ✅ Python | ✅ | ✅ |
| Extra LLM hop | ✅ yes (+cost, +latency) | ❌ no | ❌ | ❌ |
| A2A-exposable (is still an "agent") | ✅ | ✅ | ✅ | ❌ |
| Evaluable with `adk eval` | ❌ (bug #3434 on SequentialAgents too, so this is a draw) | ❌ (same bug) | ❌ | N/A |
| Build complexity (next 10 days) | HIGH (+context injection middleware, +UserContextProvider) | LOW (two callbacks + small runner) | MEDIUM | LOW |
| Debuggable | MEDIUM (LLM reasoning) | HIGH (Python stack trace) | HIGH | HIGH |
| Fits existing 2-agent shape | adds a 3rd orchestrator agent | wraps existing 2 agents as sub-agents | similar | bypasses agent model |
| Preserves A2A-first architecture commitment | ✅ | ✅ | ✅ | ❌ |

For our rules (all deterministic), LlmAgent+sub_agents adds cost and fragility with no quality gain. Bare router forfeits A2A-readiness. CustomAgent is similar to the chosen option but requires hand-writing `_run_async_impl` — SequentialAgent already does that correctly.

## Consequences

### Positive

- ~⅓ the build cost of the v1 PRD approach (no context injection middleware, no UserContextProvider, no AgentRunner abstraction).
- Deterministic: same raw text always produces the same delegation path.
- Cheap: zero additional LLM tokens for orchestration.
- Observable: callbacks emit structured `audit_event`s; OTel spans wrap each sub-agent + tool call.
- A2A-exposable later as a single agent surface.
- Reuses existing Classifier + Impact SequentialAgents unchanged — they become inner SequentialAgents that get wrapped.

### Negative

- Cannot adapt to novel delegation scenarios at runtime — any new rule requires a code change (intentional for Tier 1 rigor).
- Cannot run `adk eval` against the pipeline as a whole (ADK bug #3434). Mitigated with a pytest integration test. Individual Classifier + Impact evalsets still apply.
- Short-circuit pattern relies on `before_agent_callback` returning `Content` — behavior pinned to current ADK version. Flagged as a test to add (U-11 … U-13 in test-plan.md).
- If Tier 2 Supermemory / context injection lands, the callback pattern will need to accommodate richer state — should still compose cleanly but revisit when Rule A/D/E arrive.

### Neutral

- Same `output_schema` + two-agent (fetcher + formatter) pattern inside Classifier and Impact remains unchanged — those are separate SequentialAgents now nested inside the outer pipeline SequentialAgent.

## Implementation sketch

Reference: `docs/research/coordinator-orchestration-patterns.md` §15 has ready-to-paste code. Summary:

- `modules/triage/pipeline.py` — `create_triage_pipeline()` factory returning `SequentialAgent`.
- `modules/triage/pipeline/callbacks.py` — `_rule_b_safety_check(callback_context)` and `_rule_cf_skip_check(callback_context)`.
- `modules/triage/pipeline/_constants.py` — safety keyword list.
- `runners/triage_runner.py` — blocking `run_triage(event, user_id, company_id)` + streaming `stream_triage(event, user_id, company_id)`.
- `runners/routes/triage.py` — `POST /api/v1/triage` endpoint wiring the SSE response.

## Alternatives rejected in detail

**LlmAgent + sub_agents:** extra LLM hop adds ~1.5s + $0.003 per run. Flexible delegation is wasted since our rules are fully deterministic. The v1 PRD's full spec (context injection, UserContextProvider, AgentRunner abstraction) also required ~3-4 days of additional build — infeasible in our 10-day window.

**CustomAgent:** functionally equivalent to our choice but requires hand-writing `_run_async_impl`. SequentialAgent already ships this correctly and is better understood. Only pick CustomAgent if we need behavior SequentialAgent can't express — we don't.

**Bare Python router:** breaks A2A-readiness (you can't A2A-expose a Python function). Our architecture commitment per `project_architecture_a2a_vendor_free.md` memory + Sprint 3 A2A-forward-compat requirement rules this out.

## References

- `docs/research/coordinator-orchestration-patterns.md` — full pattern comparison, code skeletons, gotchas.
- `docs/sessions/2026-04-18-research-session-decisions.md` §4 — decision trail.
- [ADK Multi-agent systems docs](https://google.github.io/adk-docs/agents/multi-agents/).
- [ADK Sequential agents docs](https://google.github.io/adk-docs/agents/workflow-agents/sequential-agents/).
- [adk-python discussion #2290 — conditional skip](https://github.com/google/adk-python/discussions/2290).
- [adk-python issue #3434 — sub-agent trajectory eval bug](https://github.com/google/adk-python/issues/3434).
- Supersedes: design in `docs/sprints/sprint-3/prd-v1-archived.md` §2.1–§2.4.

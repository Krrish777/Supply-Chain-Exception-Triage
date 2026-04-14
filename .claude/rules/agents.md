---
description: ADK agent design — callbacks, state, composition, Gemini config, graceful degradation
paths: ["src/supply_chain_triage/modules/*/agents/**"]
---

# Agent rules

Every agent is a subpackage: `agent.py`, `prompts/*.md`, `schemas.py`, `tools.py`. Co-located, not central. `prompts/` is a folder of markdown files (not a single `prompt.py`) — chosen for long multi-section prompts and diff readability.

## 1. Callback placement

Five ADK hooks, each with distinct return semantics:

| Hook | `None` returned | Object returned |
|---|---|---|
| `before_agent_callback` | proceed | `types.Content` — skip agent, use as final output |
| `before_model_callback` | proceed | `LlmResponse` — skip LLM, use as response |
| `after_model_callback` | use LLM output | `LlmResponse` — replace LLM output |
| `before_tool_callback` | proceed | `dict` — skip tool, use as tool result |
| `after_tool_callback` | use tool output | `dict` — replace tool output |

**Canonical uses:**
- `before_agent` — load exception context from Firestore into `state`, request-scoped setup, audit log entry.
- `before_model` — input guardrails, PII redaction, prompt validation, cached-response short-circuit.
- `after_model` — format enforcement (`output_schema` validation recovery), strip hallucinated fields, add disclaimers.
- `before_tool` — argument validation, authz, cost caps, mocked responses in tests.
- `after_tool` — normalize results, mask secrets, translate error schemas.

**Never** put business logic in callbacks (belongs in tools). **Never** put retry loops in `after_model` (use `LoopAgent`). **Never** Firestore-write in `before_model` (latency on critical path).

## 2. State namespacing

`session.state` is a string-keyed, JSON-serializable dict. Prefixes scope lifetime:

| Prefix | Scope |
|---|---|
| none | session-scoped |
| `user:` | per user across sessions (same `app_name`) |
| `app:` | global to the app |
| `temp:` | this invocation only, never persisted |

**Module-scoped keys for this project:** `triage:exception_id`, `triage:classification`, `triage:impact`, `triage:resolution`. When `port_intel/` lands under Meta-Coordinator, use `port_intel:*` — the prefix prevents collisions.

## 3. Never mutate `session.state` directly

Inside tools and callbacks, mutate via the context:
```python
tool_context.state["triage:severity"] = "HIGH"
```
Not:
```python
session.state["triage:severity"] = "HIGH"  # WRONG — bypasses event tracking and persistence
```
ADK captures context mutations as `EventActions.state_delta` and writes atomically through `SessionService`.

## 4. Cross-agent data passing

Standard pattern: `output_key=` on the upstream agent auto-writes the final output to `state[output_key]`. Downstream agents reference `{output_key}` in their instruction template.

```python
classifier = LlmAgent(name="classifier", ..., output_key="triage:classification")
impact = LlmAgent(
    name="impact",
    instruction="Given {triage:classification}, assess business impact...",
    output_key="triage:impact",
)
pipeline = SequentialAgent(sub_agents=[classifier, impact])
```

Keep large domain objects in Firestore keyed by ID; store only the ID + small derived fields in state.

## 5. Structured output + tools mutual exclusion on Gemini 2.5 Flash

`output_schema` on an `LlmAgent` forbids tools or sub-agent transfer. Gemini 3.0 lifts this, but Flash does not. **Canonical workaround (two-agent pattern):**

```python
fetcher = LlmAgent(
    name="fetcher",
    tools=[lookup_exception],
    output_key="raw_exception",
)
formatter = LlmAgent(
    name="formatter",
    instruction="Format {raw_exception} as JSON matching the schema.",
    output_schema=ClassificationOutput,
    output_key="triage:classification",
)
classifier = SequentialAgent(sub_agents=[fetcher, formatter])
```

**Recovery when structured output breaks** (long prompts, deeply nested schemas, union types): validate in `after_model_callback` with `try: Model.model_validate_json(...)`; on failure, return a corrective `LlmResponse` or escalate via `LoopAgent`.

Keep Tier 1 schemas **flat** — primitives, short enums, no deep nesting, no untagged unions.

## 6. Agent composition

| Type | When to use |
|---|---|
| `SequentialAgent` | Deterministic pipeline (Classifier → Impact) |
| `ParallelAgent` | Fan-out independent work (Impact + Route-Optimization on same exception in Tier 3) |
| `LoopAgent` | Until convergence (Tier 2 Generator-Judge, `max_iterations` + judge escalates `escalation_action` to exit) |
| `LlmAgent` with `sub_agents=[...]` | LLM-decided routing (Coordinator) — picks child based on each child's `description=` |

## 7. Terse-coordinator rule

Coordinator instruction stays under ~20 lines. Delegation logic goes in each **child's** `description=` field, which is what the Coordinator LLM actually sees when routing.

Bad: 200-line coordinator prompt that restates every child's behavior.
Good: 10-line router + rich per-child `description=` strings.

## 8. Thinking-budget defaults per role (Gemini 2.5 Flash)

```python
from google.genai.types import GenerateContentConfig, ThinkingConfig

# Classifier / Impact — structured, fast
GenerateContentConfig(thinking_config=ThinkingConfig(thinking_budget=1024))

# Resolution Generator (Tier 2) — creative, longer reasoning
GenerateContentConfig(thinking_config=ThinkingConfig(thinking_budget=4096))

# Judge (Tier 2) — fast pass/fail
GenerateContentConfig(thinking_config=ThinkingConfig(thinking_budget=0))

# Comms drafter (Tier 3)
GenerateContentConfig(thinking_config=ThinkingConfig(thinking_budget=1024))
```

## 9. Safety settings

Default Gemini thresholds block logistics terms like "strike", "hazard cargo". For internal supply-chain content, loosen to `BLOCK_ONLY_HIGH`:

```python
from google.genai.types import SafetySetting, HarmCategory, HarmBlockThreshold

safety_settings = [
    SafetySetting(
        category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH,
    ),
    # ... same pattern for other categories
]
```

## 10. Streaming

Stream tokens only from the **final** agent. Never stream intermediate `SequentialAgent` steps — it leaks raw JSON fragments to users.

FastAPI pattern: wrap `Runner.run_async` as an async generator, emit SSE (`text/event-stream`), filter on `event.is_final_response()` + `event.partial`.

## 11. Never hand-write A2A

When an A2A surface is needed (Tier 3): `uvx agent-starter-pack create ... --agent adk_a2a`. Lift scaffolded files into `runners/`. Artifacts that are **never** hand-written:

- `A2aAgentExecutor`
- `AgentCardBuilder`
- `agent.json`
- `A2AFastAPIApplication` mount
- Agent Engine CI/CD glue

## 12. Graceful degradation

If a sub-agent fails, the Coordinator must still return whatever it has. Concrete rule for triage:

> If `{triage:impact}` is missing in state, the Coordinator returns classification only with `impact_available=false`. Never 500.

Model this via Coordinator instruction:
> "If `{triage:impact}` is not present, report classification only and note the impact assessment was unavailable."

## 13. No direct Firestore/Firebase imports

`agent.py` imports `from google.adk.*`. It does **not** import `firebase_admin` or `google.cloud.firestore`. All data access goes through tools. Enforced by ruff `TID251` — see `.claude/rules/imports.md`.

# ADK + Gemini Best Practices

> Date: 2026-04-16
> Context: Compiled during Sprint 1 Classifier development. Covers patterns
> we're using and patterns we should adopt.

## 1. Two-Agent Pattern (Fetcher + Formatter)

**What we do:** `SequentialAgent(sub_agents=[fetcher, formatter])`
**Why:** Gemini 2.5 Flash can't combine `output_schema` + tools on one agent.

### Best practices (confirmed by ADK docs + Google blog)

- **Unique `output_key` per agent** — prevents race conditions in shared state.
  We use `triage:raw_exception_data` (fetcher) and `triage:classification` (formatter).
- **`include_contents="none"` on formatter** — avoids sending fetcher's tool call
  history to the formatter, which would trigger the "function calling with JSON
  mime type" error on Gemini 2.5.
- **Clear history via `before_model_callback`** — defense-in-depth alongside
  `include_contents="none"`. Sets `llm_request.contents = []`.
- **Factory function for agent creation** — `create_classifier()` instead of
  module-level instances. Prevents "agent already has parent" errors when
  composing into a Coordinator later.

**Sources:**
- [Multi-agent patterns in ADK — Google Blog](https://developers.googleblog.com/developers-guide-to-multi-agent-patterns-in-adk/)
- [ADK SequentialAgent docs](https://adk.dev/agents/workflow-agents/sequential-agents/)
- [ADK State docs](https://adk.dev/sessions/state/)

---

## 2. State Management

### Prefix conventions

| Prefix | Scope | Our usage |
|--------|-------|-----------|
| (none) | Session-scoped | `triage:classification`, `triage:raw_exception_data` |
| `user:` | Per-user across sessions | Not used yet |
| `app:` | Global | Not used yet |
| `temp:` | Current invocation only | `temp:classifier:start_perf_ns`, token counters |
| `cache:` | Per-turn Firestore cache | `cache:exception:<id>`, `cache:company:<id>` |

### Best practices

- **Mutate via context objects** — `tool_context.state["key"] = value` or
  `callback_context.state["key"] = value`. Never `session.state["key"]` directly
  (bypasses event tracking).
- **`{state_key}` in instructions** for template injection — ADK resolves at runtime.
- **Module-scoped keys** — `triage:*` prefix prevents collisions when
  `port_intel:*` lands later.

**Source:** [ADK State docs](https://adk.dev/sessions/state/)

---

## 3. Callback Design Patterns

### What we use

| Callback | Agent | Purpose |
|----------|-------|---------|
| `before_agent` | classifier (outer) | Start perf timer |
| `after_model` | fetcher + formatter | Accumulate token usage |
| `before_model` | formatter | Clear conversation history |
| `after_agent` | classifier (outer) | Severity clamp, safety scan, confidence gate, logging |

### Best practices from ADK docs

1. **Single responsibility** per callback — don't mix logging with validation.
2. **Never block** — callbacks run synchronously in the agent loop. No I/O in
   `before_model` (we correctly skip Firestore here).
3. **Wrap in try-catch** — a crashing callback kills the agent run. Set state
   flags instead of raising.
4. **Idempotent** — framework may retry; side effects should handle duplication.
5. **Parameter names must match exactly** — ADK uses keyword args. Never rename
   `callback_context` to `_callback_context`. Use `# noqa: ARG001` instead.

### Anti-patterns to avoid

- Business logic in callbacks (belongs in tools)
- Retry loops in `after_model` (use `LoopAgent`)
- Firestore writes in `before_model` (latency on critical path)
- Raising exceptions from callbacks (kills agent run)

**Source:** [ADK Callback Patterns](https://adk.dev/callbacks/design-patterns-and-best-practices/)

---

## 4. Structured Output (Gemini 2.5 Flash)

### Schema design rules

- **No `dict[str, Any]`** — use `list[KeyValueModel]` or flat Pydantic models
- **Nesting depth <= 2** — reliability drops sharply past that
- **Short enum values** — under ~30 chars each, under ~100 total values
- **Max 100 properties** per schema
- **Put `reasoning` field last** — forces model to analyze before classifying
- **`extra="forbid"` on schema** — but be aware Gemini may add fields

### Few-shot examples in prompts

- **3-5 diverse examples** covering each classification category
- **Positive phrasing** — "classify as X when..." not "don't classify as Y"
- **Fictional but plausible values** — no real BOL numbers or carrier IDs
- **Zero-shot first** — only add few-shot if zero-shot F1 is insufficient
- **Role prompting has negligible effect on classification** — keep role section
  to 1-3 lines

**Sources:**
- [Gemini Prompt Strategies](https://ai.google.dev/gemini-api/docs/prompting-strategies)
- [Gemini 2.5 Flash Developer Guide](https://www.shareuhack.com/en/posts/gemini-2-5-flash-developer-guide-2026)
- [Prompt Engineering Best Practices 2026](https://promptbuilder.cc/blog/prompt-engineering-best-practices-2026)

---

## 5. Tool Design

### What we follow

- **Return contract:** `{"status": "success"|"error"|"retry", "data": {...}}`
- **Async for I/O** — all Firestore tools are `async def`
- **Per-turn cache** — `tool_context.state[f"cache:{key}"]` avoids N+1 reads
- **`ToolContext` as runtime import** — ADK introspects signatures at runtime

### Best practices

- **Tool docstring = LLM-facing description** — treat as prompt engineering
- **Type hints = parameter schema** — clear types, no defaults
- **Don't mention `tool_context` in docstring** — but DO include it as a param
  (ADK strips it from the LLM-facing schema automatically)
- **Error classification at boundary** — transient (retry), permanent (error),
  unexpected (let it raise)

**Source:** [ADK Custom Tools](https://adk.dev/tools-custom/function-tools/)

---

## 6. Evaluation Strategy

### What to use for each agent type

| Agent type | Evaluation method |
|-----------|-------------------|
| Leaf agent (classifier) | `adk eval` with evalset |
| Coordinator | Rubric-based only (trajectory scoring broken — adk-python#3434) |
| Tools | pytest unit tests |
| Callbacks | pytest unit tests |

### Evalset best practices

- **Capture-then-edit** — drive scenarios in `adk web`, export session, edit JSON
- **One assertion per rubric** — binary yes/no, never compound
- **`num_samples: 5`** for standard rubrics, **9 for safety**
- **Never `response_match_score`** on free text — use `final_response_match_v2`
- **15-25 cases** per leaf agent (happy + edge + safety + adversarial)
- **`temperature=0`** for all eval runs
- **Embed `prompt_sha256`** in session_input.state for drift detection

### Metrics

| Metric | Best for |
|--------|---------|
| `tool_trajectory_avg_score` | Deterministic tool sequences (fetcher) |
| `rubric_based_final_response_quality_v1` | Classification quality assertions |
| `final_response_match_v2` | Semantic response comparison |
| `hallucinations_v1` | Grounding checks |
| `safety_v1` | Harmful content (pair with custom adversarial rubric) |

**Sources:**
- [ADK Evaluation docs](https://adk.dev/evaluate/)
- [ADK Eval Criteria](https://adk.dev/evaluate/criteria/)
- [ADK Eval Codelab](https://codelabs.developers.google.com/adk-eval/instructions)

---

## 7. Production Readiness Checklist

Things to add before Tier 1 ships:

- [ ] **Review agent pattern** — add a critic/reviewer agent for Tier 2 that
      validates classification quality
- [ ] **Fallback on schema validation failure** — `after_model_callback` catches
      `ValidationError`, returns safe defaults (CRITICAL + requires_human)
- [ ] **Token budget monitoring** — track `usage_metadata` per agent per day
- [ ] **Idempotent callbacks** — ensure retries don't double-count tokens
- [ ] **Error recovery in SequentialAgent** — if fetcher fails, formatter
      shouldn't run on empty state

---

## 8. Thinking Budget Guidance

| Agent role | Budget | Rationale |
|-----------|--------|-----------|
| Fetcher (tool-calling) | 1024 | Needs reasoning for tool selection |
| Formatter (classification) | 0 | Pure schema-filling, no reasoning needed |
| Judge (Tier 2) | 0 | Pass/fail, fast |
| Generator (Tier 2) | 4096 | Creative resolution generation |
| Coordinator | 1024 | Routing decisions |

`budget=0` costs $0.60/1M tokens vs $3.50/1M for thinking tokens (5.8x cheaper).

**Source:** [Vertex AI Thinking docs](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/thinking)

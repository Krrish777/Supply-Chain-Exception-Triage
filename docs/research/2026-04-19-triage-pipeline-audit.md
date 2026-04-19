# Triage Pipeline — Deep Audit (2026-04-19)

> **Trigger:** Triage run `session-669bc958-cd7a-4307-93bb-0cdc9f00d52a.json` for `EXC-2026-0004` produced a near-empty, wrong classification despite the event being a CRITICAL chemical tanker safety incident. This doc captures the audit, research, and root-cause analysis.
>
> Companion plan lives in `.claude/plans/session-669bc958-cd7a-4307-93bb-0cdc9f0-deep-hoare.md`.

## 1. Evidence — What the failing trace shows

### 1.1 Trace timeline

| Step | Author | Action |
|---|---|---|
| 1 | user | message `"Triage exception EXC-2026-0004"` |
| 2 | classifier_fetcher | called `get_exception_event("EXC-2026-0004")` → `{"status":"error","error_message":"Exception event 'EXC-2026-0004' not found"}` |
| 3 | classifier_fetcher | wrote a briefing with `Company Context: Not available`. **`get_company_profile` was never called** because the event lookup failed → no `company_id` was extracted. |
| 4 | classifier_formatter | produced `customer_escalation/delivery_complaint`, `LOW`, `confidence=0.55`, `tools_used=[]`. |
| 5 | impact_fetcher | called **zero tools** and emitted prose `"unable to retrieve impact data… no valid scope"`. |
| 6 | impact_formatter | wrote an empty `ImpactResult` with all zeros. |

The actual event (per `scripts/seed_classifier_demo.py`, EXC-2026-0004) is a chemical tanker overturn with driver injury, chemical spill, and 3 trucks blocked — a CRITICAL safety incident. The pipeline produced the opposite.

### 1.2 Code-level findings

**Classifier fetcher prompt** (`agents/classifier/prompts/system_fetcher.md` lines 14-27) — Mode B tells the model to *skip all tools* whenever it interprets the input as raw text:

> **Mode B — Raw exception text provided:** … **skip the tool calls entirely**. Use the user's message as the raw exception content and compile the briefing directly from it. Most users will paste raw exception text (Mode B). Use Mode A only when the message clearly contains just an event ID reference.

There is **no Mode A fallback path** for "event not found" — the prompt assumes Mode A succeeds.

**Classifier formatter examples** (`prompts/system_formatter.md` lines 98-217) — every example sets `"tools_used": []`. With `include_contents="none"` + `_clear_history` on the formatter (`agent.py:218-228`), the formatter cannot see which tools the fetcher invoked, so `tools_used` is always a guess.

**Impact fetcher prompt** (`agents/impact/prompts/system_fetcher.md` lines 23-77) — Mode A relies on `key_facts` containing `vehicle_id`, `route_id`, or `region`. When `{triage:classification}` is present but `key_facts = [{"key":"event_id", …}]` (no scope), there is **no fallback to Mode B** (call `get_exception_event`, extract scope from `raw_content`). Model gave up.

**Pipeline Rule B** (`pipeline/callbacks.py` `_rule_b_safety_check`) — scans `state["triage:event_raw_text"]`, seeded from the API payload's `raw_text`. In this trace `raw_text=""` (only `event_id` was supplied), so Rule B saw an empty string and did nothing — even though the *real* event content contains `overturned`, `injured`, `spill`, `chemical leak` (all Rule B keywords). **Rule B is blind to events looked up by ID alone.**

**Tool duplication** — `get_exception_event` is defined twice (classifier/tools.py and impact/tools.py) and they drift. `modules/triage/tools/` exists but only has `__init__.py`; the codebase rules call for a shared tools layer there.

**Seed data gap** — `seed_emulator.py` only seeds 2 events (0001, 0002). `seed_classifier_demo.py --live` seeds 5 events (0001-0005, including 0004). If the user ran `seed_emulator.py`, `EXC-2026-0004` does not exist → "not found" was a seed problem compounded by a code bug that handled not-found badly.

**Schema vs prompt drift** — `ClassificationResult.tools_used` exists in the schema (`Field(default_factory=list)`) — the model fills it from prompt examples, not from runtime introspection.

### 1.3 Natural-language input is also structurally broken

Independent of EXC-2026-0004:

- `POST /api/v1/triage` accepts `{event_id, raw_text}`. If no `event_id`, the API synthesizes `f"adhoc-{uuid4().hex[:16]}"` and passes raw_text into state.
- **But the LLM trigger message is always `f"Triage exception {event_id}"`** — the actual user text never reaches the LLM as the trigger.
- The classifier's Mode B then treats that synthetic trigger string as "the user's message" and produces garbage classification.

So a user pasting *"Chemical tanker overturned on NH8 near Vapi, our 3 trucks stuck"* today produces a wrong classification for a different reason than the EXC-2026-0004 trace — same overall failure shape.

## 2. Research — Best practices we are not fully following

### 2.1 ADK `before_agent_callback` is the canonical state-hydration hook

`before_agent_callback` "is called immediately before the agent's execution method… ideal for setting up resources or state needed for the agent's run". State writes via `callback_context.state[...]` are tracked in `Event.actions.state_delta` and persisted through `SessionService`. Returning `Content` from this callback skips the agent (which is how our Rule B already works).

**Implication for us:** pre-fetch event + company deterministically before any LLM call, so:
- Rule B scans the actual `raw_content`, not empty `raw_text`.
- Classifier doesn't rely on the LLM picking Mode A vs Mode B correctly.
- Impact doesn't rely on the LLM extracting scope correctly.

### 2.2 `{state.key}` template substitution is preferred over forcing tool calls for known data

ADK's `instruction` strings support `{state.key}` substitution (with `{state.key?}` for optional). Our impact formatter already uses this for `{raw_impact_data}` and `{triage:classification}`. The classifier fetcher does **not** — its prompt relies on Mode A vs Mode B branching instead of state injection. Tool-calling for context the system already knows is more brittle than substitution.

### 2.3 The two-agent fetcher/formatter pattern works only if the formatter sees the fetcher's data

`_clear_history` zeroes the formatter's contents to save tokens — correct, per ADK discussion #3457 — but it means the formatter **must** be fed everything it needs via `{state.X}` injection. Today the formatter sees `{raw_exception_data}` (the briefing string) but not the actual tools-used list. Hence `tools_used: []` is a guess.

### 2.4 Tool-error guidance must be explicit in the prompt

Industry pattern (LangChain, LangGraph, Anthropic): when a tool returns an error, the prompt must tell the model exactly what to do next — retry with different args, try a sibling tool, fall through to a deterministic fallback, or escalate. Otherwise the model silently proceeds with degraded context — exactly what we saw in the trace.

### 2.5 Gemini 2.5 Flash: `output_schema` and `tools` are mutually exclusive

From the ADK cheatsheet: *"Using `output_schema` disables tool calling and delegation."* Gemini 3 lifts this restriction; Flash does not. Our two-agent workaround is correct for the chosen model. If/when we migrate to Gemini 3, we can collapse each pair into a single agent.

### 2.6 `{triage:key}` rendering: state keys with colons work

Our state keys use a `triage:` prefix. ADK's substitution supports colons. We already use `{triage:classification}` in the impact formatter. So `{triage:event_raw_content}`, `{triage:company_markdown}` etc. are safe.

## 3. Root causes — Ranked

| # | Root cause | Symptom | Priority |
|---|---|---|---|
| **R1** | No deterministic event hydration: pipeline trusts the LLM to look up the event and extract `company_id`/scope, no fallback on failure. | `Company Context: Not available`; impact fetcher could not find scope. | **P0** |
| **R2** | Classifier fetcher Mode B says "skip tool calls entirely" → company profile never fetched for raw-text input, even when `metadata.company_id` is known. | Trips on every raw-text exception, not just this one. | **P0** |
| **R3** | Rule B scans `triage:event_raw_text` (empty when only `event_id` is supplied). Real safety content stays invisible. | Chemical tanker overturn misclassified as `customer_escalation/LOW`. | **P0** |
| **R4** | Impact fetcher Mode A has no fallback to Mode B when classification has no scope key. | `impact_fetcher` called zero tools. | **P0** |
| **R5** | `tools_used` is filled by the formatter, not from runtime introspection. With `include_contents="none"`, the formatter cannot know what was called. | `tools_used: []` despite the tool being called. | P1 |
| **R6** | Natural-language input never reaches the LLM as the trigger — runner sends `f"Triage exception {event_id}"` regardless. | End-user NL input is silently wrong. | **P0** |
| **R7** | Seed gap: `seed_emulator.py` missing 3 of 5 demo events (0003, 0004, 0005) + NimbleFreight. | Tool returned "not found". | P1 |
| **R8** | `get_exception_event` duplicated in classifier and impact tools modules; no shared tools layer. | Drift risk. | P2 |
| **R9** | No "broaden scope" retry in impact despite the prompt mentioning it. | Silent zero-shipment result. | P2 |
| **R10** | Formatter examples teach `tools_used: []` regardless of what was called. | Same as R5. | P2 |
| **R11** | No pipeline-level evals (only per-agent). | This regression slipped through. | P2 |

## 4. Firestore data coverage — what's there, what's missing

### What's there
- `companies/swiftlogix-001` — profile OK.
- `exceptions/EXC-2026-0001` and `EXC-2026-0002` (via `seed_emulator.py`).
- Via `seed_classifier_demo.py --live`: EXC-2026-0001..0005.
- Via `seed_impact_demo.py --live`: customers, routes, hubs, shipments, NimbleFreight company.

### What's missing / weak
- `seed_emulator.py` (the convenience all-in-one) misses events 0003, 0004, 0005 and NimbleFreight. **Single source of truth needed.**
- Exception documents have `metadata.company_id` (good), but no `affected_vehicle_id` / `affected_route_id` / `affected_region` structured fields — today, scope is LLM-inferred from `raw_content`. Adding these fields would let the hydrator pre-resolve scope deterministically. *(Deferred — not required for this fix.)*
- `customers.json` customer_ids (e.g. `cust_blushbox`) are the canonical keys; `companies/swiftlogix-001.customer_portfolio.top_customers` lists names rather than IDs. Fine for classifier, but worth noting for future cross-linking.
- No `vehicles/` collection or index. `get_affected_shipments` queries `shipments where status="in_transit" and vehicle_id==X` directly — works for current scale; production would want a composite index in `infra/firestore.indexes.json`. *(Deferred.)*

## 5. Sources

- [ADK Callbacks: Observe, Customize, Control](https://google.github.io/adk-docs/callbacks/)
- [ADK Callback patterns + best practices](https://google.github.io/adk-docs/callbacks/design-patterns-and-best-practices/)
- [ADK Types of callbacks](https://google.github.io/adk-docs/callbacks/types-of-callbacks/)
- [ADK Session State](https://google.github.io/adk-docs/sessions/state/)
- [ADK Sequential agents](https://google.github.io/adk-docs/agents/workflow-agents/sequential-agents/)
- [ADK LLM agents (instruction template substitution)](https://google.github.io/adk-docs/agents/llm-agents/)
- [ADK GitHub discussion #3457 — clearing history when using output_key + template vars](https://github.com/google/adk-python/discussions/3457)
- [Smarter ADK prompts: inject state and artifact data](https://dev.to/masahide/smarter-adk-prompts-inject-state-and-artifact-data-dynamically-placeholders-2dcm)
- [Gemini structured output docs](https://ai.google.dev/gemini-api/docs/structured-output)
- [LangGraph error handling: retries & fallbacks](https://machinelearningplus.com/gen-ai/langgraph-error-handling-retries-fallback-strategies/)
- [Addressing tool errors via prompts (apxml)](https://apxml.com/courses/prompt-engineering-agentic-workflows/chapter-3-prompt-engineering-tool-use/addressing-tool-errors-via-prompts)

## 6. Approved fix — summary

1. Pre-fetch event + company in an async `before_agent_callback` (Path A: event_id lookup; Path B: natural-language input with `company_id` from auth claims).
2. List-of-callbacks on the pipeline: `[_hydrate_event, _rule_b_safety_check]`.
3. Rewrite classifier and impact fetcher prompts around hydrated state, with explicit tool-error guidance and Mode A → Mode B fallback.
4. Drop `tools_used` from both schemas (not load-bearing; can't be filled accurately).
5. Consolidate `get_exception_event` + `get_company_profile` into `modules/triage/tools/lookup.py`.
6. Single seed source (`scripts/seed/exceptions.json`) + update both seed scripts to read from it.
7. Unit + integration + evalset coverage.

Full plan: `.claude/plans/session-669bc958-cd7a-4307-93bb-0cdc9f0-deep-hoare.md`.

---
title: ADK before_model_callback — dynamic context injection for Coordinator
type: zettel
tags: [adk, coordinator, context-injection, gemini, zettel]
status: first-principles
last_updated: 2026-04-14
confidence: high
sources:
  - https://google.github.io/adk-docs/callbacks/types-of-callbacks/
  - https://google.github.io/adk-docs/callbacks/
  - https://github.com/google/adk-docs/blob/main/examples/python/snippets/callbacks/before_model_callback.py
  - https://google.github.io/adk-docs/sessions/state/
related:
  - "[[adr-003-prompt-format]]"
  - "[[Supply-Chain-Agent-Spec-Coordinator]]"
  - "[[zettel-supermemory-python-sdk]]"
---

# ADK before_model_callback — dynamic context injection for Coordinator

> **TL;DR.** `before_model_callback` runs just before the LLM request goes out. Mutate `llm_request.config.system_instruction` (or return an `LlmResponse` to short-circuit). This is where our Coordinator's 5 XML dynamic blocks (`<user_context>`, `<company_context>`, `<recent_history>`, `<learned_behaviors>`, `<runtime_context>`) get rendered from Supermemory + Firestore + current time and injected into the prompt.

## First principles

**Why callbacks and not just prompt-assembly?** The LLM request is a contract between your agent and the model. You could render the full prompt at agent instantiation, but then user/company context would be stale, session state wouldn't flow in, and you'd re-render for every request even if inputs didn't change. The callback lets you *intercept the contract at the last moment*, pull fresh context, and splice it in.

**Two injection mechanisms — pick per use case:**

1. **`{key}` placeholders in `instruction`** (simplest). Framework auto-replaces from `session.state` before LLM call. Use for scalar values: `timestamp`, `user_id`, `company_id`.
2. **`before_model_callback` function** (full control). Needed for complex rendering: fetching Supermemory, running `UserContext.to_markdown()`, constructing XML blocks with escaping. Required for our Coordinator.

## Signature

```python
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest

async def inject_coordinator_context(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> None:
    # Read session state (mutable)
    company_id = callback_context.state["company_id"]
    user_id = callback_context.state["user_id"]

    # Fetch fresh context (Supermemory + Firestore)
    user_ctx = await memory.fetch_user_context(user_id, company_id)
    company_profile = await memory.fetch_company_profile(company_id)

    # Render XML blocks (HTML-escape dynamic values — prompt-injection defense)
    context_blocks = (
        f"<user_context>\n{escape(user_ctx.to_markdown())}\n</user_context>\n"
        f"<company_context>\n{escape(company_profile.to_markdown())}\n</company_context>\n"
        f"<runtime_context>\n- timestamp: {datetime.utcnow().isoformat()}\n</runtime_context>"
    )

    # Mutate the request — prepend to system_instruction
    llm_request.config.system_instruction += "\n\n" + context_blocks

root_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="coordinator",
    instruction=STATIC_COORDINATOR_PROMPT,        # Markdown hierarchy (ADR-003)
    before_model_callback=inject_coordinator_context,
    sub_agents=[classifier_agent, impact_agent],
)
```

## Project implications

1. **Coordinator prompt is two-part.** `instruction=` carries the static Markdown (role, architectural rules, delegation rules A–F, output format). Callback appends the dynamic XML blocks. This matches the hybrid Markdown-XML split in ADR-003.
2. **Callback lives beside the agent definition.** Path: `modules/triage/agents/coordinator/agent.py` (with callback as a local function or imported from `modules/triage/agents/coordinator/callbacks.py` if it grows).
3. **Session state is where `user_id`, `company_id`, and `event_id` flow in** — set by the FastAPI route handler before invoking the agent, read by the callback. Namespace per `.claude/rules/agents.md` §2.
4. **Callbacks can short-circuit** — return an `LlmResponse` and the LLM call is skipped entirely. Use for Rule B (safety override): if safety keywords detected, return a synthetic `LlmResponse` that triggers `escalated_to_human_safety` without consulting Gemini. Cheaper + more deterministic.
5. **Pytest unit test callbacks as plain functions** (per `.claude/rules/testing.md` §7). Mock `CallbackContext` and `LlmRequest`, assert mutations. Agents themselves use evalsets, not pytest.

## Gotchas flagged

- **Session state mutations tracked as events.** `callback_context.state['key'] = value` creates a framework event. Don't use callback state as a scratchpad for things that aren't audit-worthy.
- **Dynamic model/tool swapping is the wrong tool here** — there's an open `adk-python#3647` about runtime model/tool changes. We only need to change *instructions*, which the callback supports cleanly.
- **Prompt-injection defense.** The `<user_context>` block contains Supermemory data that itself came from user inputs in the past. Escape `<` and `>` in injected values before inserting into the XML block, or a crafted past exception could inject fake instructions.
- **Callback ordering.** `before_agent_callback` → `before_model_callback` → LLM → `after_model_callback` → `after_agent_callback`. For context injection, `before_model_callback` is the right hook (after the model request is assembled but before it's sent).

## Further research

- **Streaming compatibility.** When Sprint 4 adds SSE, does `before_model_callback` run once per streaming session, or once per chunk? Docs imply once per request; verify in prototype.
- **Callback + `AgentEvaluator`.** Evalsets run agents end-to-end — do they invoke callbacks? If yes, evalsets need fixture Supermemory data. If no, we have a behavioral gap between evalset and prod.
- **Cross-module callback sharing.** Tier 2 Resolution agent might want the same `inject_common_context` callback. Where would a shared-callback library live? `modules/triage/common/` (not currently in placement table)?
- **Session persistence.** How does session state persist across multiple turns in a single user conversation? Does it persist across user sessions?

## Related decisions

- **ADR-003 Prompt format** — the Markdown-vs-XML split this callback operationalizes.
- **ADR-002 Memory layer** — the callback is the entry point where Supermemory data enters the prompt.
- **`.claude/rules/agents.md` §1 (Callback placement)** — project rule on where callback code lives.

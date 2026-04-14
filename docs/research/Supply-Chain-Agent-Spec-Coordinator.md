---
title: "Agent Spec: Module Coordinator (Tier 1)"
type: deep-dive
domains: [supply-chain, agent-design, hackathon]
last_updated: 2026-04-10
status: active
confidence: high
sources: ["[[Supply-Chain-Demo-Scenario-Tier1]]", "[[Supply-Chain-Product-Recap]]", "[[Supply-Chain-Architecture-Decision-Analysis]]"]
---

# Agent Spec: Module Coordinator (Tier 1)

> [!abstract] Research-Backed Specification
> Complete specification for the Module Coordinator agent in the Exception Triage Module. All design decisions are backed by 2026 web research (cited below) and user domain knowledge, not model knowledge alone. This is the authoritative spec for Tier 1 implementation.

## Role in the Architecture

The Module Coordinator is the entry point for exception triage. It receives raw exception events, orchestrates specialist agents (Classifier, Impact), enforces delegation rules, and returns a structured triage result to the UI via streaming SSE.

```
Exception Event → Coordinator → [Classifier → Impact] → Triage Result (streamed)
                       ↑
              Dynamic user/company context
              (from Supermemory)
```

## Framework & Tech Stack

| Layer                   | Choice                                         | Reasoning                                                  |
| ----------------------- | ---------------------------------------------- | ---------------------------------------------------------- |
| Agent framework         | **Google ADK** `LlmAgent`                      | Native Gemini support, SC alignment, 163 notes of research |
| Sub-agent pattern       | ADK `sub_agents` with AutoFlow                 | LLM-driven delegation, built into ADK                      |
| Deterministic sub-flows | ADK `SequentialAgent` (if needed post-Tier 1)  | No LangGraph/BeeAI needed — ADK has it built-in            |
| LLM                     | Gemini 2.5 Flash                               | Fast, cheap, sufficient for coordination                   |
| Memory                  | Supermemory (via `MemoryProvider` abstraction) | Sub-300ms retrieval, native connectors                     |
| Validation              | Guardrails AI                                  | Structured JSON validation, auto-correction                |
| Streaming               | Hybrid SSE + Gemini text streaming             | Best demo drama + UI parseability                          |
| Prompt format           | Hybrid Markdown + XML delimiters               | Research-backed (see citations)                            |

## Delegation Rules (India-Localized, 6 Rules Approved)

### Rule A: WhatsApp Voice Priority
Exceptions arriving via `source_channel == "whatsapp_voice"` get an urgency hint injected into the Classifier context: *"Received via WhatsApp voice — likely operational urgency."*

### Rule B: Driver Safety Override
If the exception raw text contains safety keywords (injury, accident, threat, emergency in English/Hindi/Hinglish), bypass all specialists and set `status: "escalated_to_human_safety"`. Safety beats everything.

### Rule C: Regulatory Auto-Escalate Impact
If Classifier identifies `subtype in ["eway_bill_issue", "gst_noncompliance", "customs_hold"]`, always delegate to Impact Agent — even for LOW severity. Compliance issues have cascading legal risk.

### Rule D: Festival/Monsoon Temporal Context
Coordinator reads current date, checks `festival_calendar.json` and `monsoon_regions.json`, and injects temporal context into specialist calls during active festival/monsoon periods.

### Rule E: D2C Reputation Risk Flagging
If Impact Agent identifies a D2C customer with a public-facing deadline (campaign launch, product launch, social media event), Coordinator elevates it in the summary with `escalation_priority: "reputation_risk"`.

### Rule F: LOW Severity Skip Impact (with Rule C override)
If Classification is LOW severity AND no customer-facing shipments affected AND subtype is NOT a regulatory issue (Rule C), skip Impact Agent to save latency and cost.

**Conflict resolution order:** Rule B > Rule C > Rule F. Rules A, D, E are additive hints that don't override.

## User Context Schema (All 5 Sections)

Stored in Supermemory per `user_id`, retrieved at runtime via middleware, injected into the Coordinator's prompt.

### Section 1: Identity
```markdown
## Identity
- Name: {name}
- Role: {role} at {company_name}
- Experience: {years_in_role} years in logistics
- Location: {city}, {state}
- Working hours: {timezone}, typically {hours_start}-{hours_end}
```

### Section 2: Volume & Workload
```markdown
## Volume & Workload
- Daily volume: {avg_daily_shipments} shipments handled
- Exception rate: {avg_daily_exceptions} per day
- Peak days: {busiest_days}
- Burden level: {workload_classification}
```

### Section 3: Communication Preferences
```markdown
## Communication Preferences
- Preferred language: {language}
- Communication style: {tone}
- Formality: {formality}
- Notification channels: {channels}
```

### Section 4: Business Context (Company Profile)
```markdown
## Business Context
- Company: {company_name}
- Size: {num_trucks} trucks, {num_employees} employees
- Regions of operation: {regions}
- Carrier network: {carriers}
- Customer portfolio: {customer_mix}
- Top priority customers: {priority_list}
- Avg daily revenue: ₹{company_avg_daily_revenue_inr}  # Used by Classifier severity validator (5% relative threshold)
```

**Important:** `company_avg_daily_revenue_inr` is required for the Classifier's relative severity threshold (Rule 3 in severity validator). Must be populated in the company profile in Supermemory before first triage request. If absent, the Classifier's severity validator skips Rule 3 and trusts the LLM's severity assessment entirely.

### Section 5: Learned Behaviors (populates over time)
```markdown
## Learned Preferences (last 30 days)
- Override patterns: {override_patterns}
- Preferred priority ordering: {learned_priorities}
- Customer relationship notes: {customer_notes}
```

## Prompt Format: Hybrid (Markdown + XML delimiters)

**Research-backed rationale:**
- [Anthropic Claude 4 Best Practices](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/claude-4-best-practices): Recommends Markdown for section hierarchy + XML tags for content boundaries
- [Delimiter Hypothesis study (March 2026)](https://systima.ai/blog/delimiter-hypothesis): XML/Markdown/JSON have statistically similar boundary scores (98.4%)
- [Markdown vs XML comparison](https://www.robertodiasduarte.com.br/en/markdown-vs-xml-em-prompts-para-llms-uma-analise-comparativa/): Markdown is ~80% cheaper in tokens than XML
- [Google Gemini prompt guide](https://dev.to/kenangain/one-stop-developer-guide-to-prompt-engineering-across-openai-anthropic-and-google-4bfb): "Gemini strongest when formatting is tightly defined at the top of the prompt"

**Decision:** Markdown headers for hierarchy + XML tags around dynamically injected content blocks. Best balance for Gemini + prompt injection defense.

## Complete System Prompt Template

```markdown
# Exception Triage Coordinator — System Instructions

## Role
You are the Exception Triage Coordinator for a supply chain operations
platform serving small 3PLs in India. You orchestrate specialist agents
(Classifier, Impact) to triage incoming exception events.

## Architectural Rules (never violate)
1. You do NOT classify exceptions yourself. Delegate to the Classifier.
2. You do NOT assess impact yourself. Delegate to the Impact Agent.
3. You do NOT fabricate shipment details, financial figures, or customer
   data. All data comes from specialist tool calls.
4. You coordinate, delegate, and synthesize — nothing more.

## Delegation Rules

### Rule A: WhatsApp Voice Priority
When `source_channel == "whatsapp_voice"`, add urgency hint when
delegating to Classifier: "Received via WhatsApp voice — likely
operational urgency."

### Rule B: Driver Safety Override (HIGHEST PRIORITY)
Before any delegation, scan the exception's raw text for safety keywords
in English, Hindi, or Hinglish (injury, accident, threat, emergency,
durghatna, ghayal, khatra). If detected, SKIP all specialists and return
status 'escalated_to_human_safety'.

### Rule C: Regulatory Auto-Escalate
If Classification subtype is in [eway_bill_issue, gst_noncompliance,
customs_hold], ALWAYS delegate to Impact Agent, even for LOW severity.

### Rule D: Festival/Monsoon Context
When delegating, include temporal context from the runtime context block
if active festival or monsoon period is flagged.

### Rule E: D2C Reputation Risk
If Impact Agent flags a D2C customer with a public-facing deadline,
elevate it in your summary with "reputation_risk" priority.

### Rule F: LOW Severity Skip Impact
If Classification severity is LOW AND no customer-facing shipments
affected AND subtype is NOT a regulatory issue (Rule C takes precedence),
you may skip the Impact Agent and return classification only.

## Conflict Resolution
Rule B > Rule C > Rule F. Rules A, D, E are additive hints.

## Output Requirements
Synthesize a structured response combining:
1. Classification result (from Classifier's session state output)
2. Impact assessment (from Impact Agent's session state output, if called)
3. A concise 2-3 sentence summary tailored to the user's context and
   communication preferences (from the injected context below)

## Safety
- Respect the user's language preference from context
- Respect the user's communication style from context
- Do not include PII beyond what the user already has access to
- Flag contradictions or low-confidence outputs explicitly

---

<user_context>
{user_context_markdown}
</user_context>

<company_context>
{company_context_markdown}
</company_context>

<recent_history>
{recent_exception_history_markdown}
</recent_history>

<learned_behaviors>
{learned_behaviors_markdown}
</learned_behaviors>

<runtime_context>
- Current timestamp: {current_timestamp}
- Active festival: {active_festival_or_none}
- Active monsoon regions: {active_monsoon_regions}
- User ID: {user_id}
- Company ID: {company_id}
</runtime_context>
```

## Implementation Architecture

### File Structure
```
supply_chain_triage/
├── agents/
│   ├── coordinator.py           # Coordinator LlmAgent definition
│   ├── classifier.py            # (next spec)
│   ├── impact.py                # (next spec)
│   └── prompts/
│       └── coordinator.md       # Static instruction template (above)
├── schemas/
│   ├── exception_event.py       # Input schema
│   ├── classification.py
│   ├── impact.py
│   └── triage_result.py         # Combined output
├── memory/
│   ├── provider.py              # MemoryProvider interface
│   └── supermemory_adapter.py   # Supermemory implementation
├── guardrails/
│   └── validators.py            # Guardrails AI validators
├── middleware/
│   └── context_injection.py     # ADK callback for dynamic context
├── runners/
│   └── agent_runner.py          # Thin abstraction for framework portability
├── api/
│   └── triage_endpoint.py       # FastAPI SSE endpoint
└── main.py
```

### Coordinator Python Code (Draft)

```python
# agents/coordinator.py
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from pathlib import Path

from .classifier import classifier_agent
from .impact import impact_agent
from memory.provider import get_memory_provider
from middleware.context_injection import build_dynamic_context

STATIC_INSTRUCTION = (Path(__file__).parent / "prompts" / "coordinator.md").read_text()


async def inject_dynamic_context(callback_context: CallbackContext) -> None:
    """
    ADK before_model_callback: retrieves user/company/session context
    from Supermemory and injects it into the system prompt for THIS call.

    Separates static architectural instructions from dynamic per-user
    context — the 2026 context engineering pattern.
    """
    user_id = callback_context.state.get("user_id")
    company_id = callback_context.state.get("company_id")

    if not user_id or not company_id:
        return  # no context to inject

    memory = get_memory_provider()

    # Build the dynamic context block from Supermemory
    dynamic_context = await build_dynamic_context(
        memory=memory,
        user_id=user_id,
        company_id=company_id,
    )

    # Override the system instruction for THIS call only
    callback_context.system_instruction_override = (
        STATIC_INSTRUCTION + "\n\n" + dynamic_context
    )


coordinator_agent = LlmAgent(
    name="ExceptionTriageCoordinator",
    model="gemini-2.5-flash",
    description=(
        "Orchestrates exception triage by delegating to Classifier and "
        "Impact specialist agents. Returns structured triage reports."
    ),
    instruction=STATIC_INSTRUCTION,  # Overridden at runtime
    sub_agents=[classifier_agent, impact_agent],
    before_model_callback=inject_dynamic_context,
)
```

## Input Schema

```python
# schemas/exception_event.py
from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime

class ExceptionEvent(BaseModel):
    event_id: str = Field(..., description="Unique ID for this exception")
    timestamp: datetime
    source_channel: Literal[
        "whatsapp_voice",
        "whatsapp_text",
        "email",
        "phone_call_transcript",
        "carrier_portal_alert",
        "customer_escalation",
        "manual_entry"
    ]
    sender: dict = Field(..., description="Sender metadata")
    raw_content: str
    original_language: Optional[str] = None
    english_translation: Optional[str] = None
    media_urls: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
```

## Output Schema

```python
# schemas/triage_result.py
from pydantic import BaseModel, Field
from typing import Literal, Optional
from .classification import ClassificationResult
from .impact import ImpactResult

class TriageResult(BaseModel):
    event_id: str
    status: Literal["complete", "partial", "escalated_to_human", "escalated_to_human_safety"]
    coordinator_trace: list[dict] = Field(default_factory=list)
    classification: Optional[ClassificationResult] = None
    impact: Optional[ImpactResult] = None
    summary: str
    processing_time_ms: int
    errors: list[str] = Field(default_factory=list)
    escalation_priority: Optional[Literal["standard", "reputation_risk", "safety", "regulatory"]] = None
```

## Streaming Event Schema (SSE)

```
event: coordinator_start
data: {"event_id": "...", "user_id": "..."}

event: coordinator_thinking
data: {"text": "streamed token chunk..."}

event: classification_ready
data: {full ClassificationResult JSON}

event: coordinator_thinking
data: {"text": "more streamed tokens..."}

event: impact_ready
data: {full ImpactResult JSON}

event: summary
data: {"text": "streamed summary tokens..."}

event: done
data: {full TriageResult JSON}
```

## Cross-References

- [[Supply-Chain-Demo-Scenario-Tier1]] — The anchor scenario this coordinator handles
- [[Supply-Chain-Product-Recap]] — Product-level overview
- [[Supply-Chain-Architecture-Decision-Analysis]] — Why D+F architecture
- Agent Specs (upcoming): Classifier, Impact

## Research Citations

**ADK & Multi-Agent Patterns:**
- [Google ADK Multi-agent systems docs](https://adk.dev/agents/multi-agents/)
- [Developer's guide to multi-agent patterns in ADK](https://developers.googleblog.com/developers-guide-to-multi-agent-patterns-in-adk/)

**Prompt Format Research:**
- [Delimiter Hypothesis study (March 2026)](https://systima.ai/blog/delimiter-hypothesis)
- [Anthropic Claude 4 Best Practices](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/claude-4-best-practices)
- [One-Stop Developer Guide — OpenAI, Anthropic, Google](https://dev.to/kenangain/one-stop-developer-guide-to-prompt-engineering-across-openai-anthropic-and-google-4bfb)
- [Markdown vs XML comparison](https://www.robertodiasduarte.com.br/en/markdown-vs-xml-em-prompts-para-llms-uma-analise-comparativa/)

**Context Engineering:**
- [LangChain Context Engineering docs](https://docs.langchain.com/oss/python/langchain/context-engineering)
- [Anthropic Effective Context Engineering for AI Agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)

**Memory Layer:**
- [Supermemory official site](https://supermemory.ai/)
- [Best Memory APIs for Stateful AI Agents 2026](https://blog.supermemory.ai/best-memory-apis-stateful-ai-agents/)
- [Mem0 vs Supermemory — LogRocket](https://blog.logrocket.com/building-ai-apps-mem0-supermemory/)

**Guardrails:**
- [Guardrails AI vs NeMo Guardrails — is4.ai (2026)](https://is4.ai/blog/our-blog-1/guardrails-ai-vs-nemo-guardrails-comparison-2026-352)
- [Production LLM Guardrails Compared — PremAI](https://blog.premai.io/production-llm-guardrails-nemo-guardrails-ai-llama-guard-compared/)

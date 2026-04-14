---
title: "Agent Spec: Classifier (Tier 1)"
type: deep-dive
domains: [supply-chain, agent-design, hackathon]
last_updated: 2026-04-10
status: active
confidence: high
sources: ["[[Supply-Chain-Demo-Scenario-Tier1]]", "[[Supply-Chain-Agent-Spec-Coordinator]]", "[[Supply-Chain-Research-Sources]]"]
---

# Agent Spec: Classifier Agent (Tier 1)

> [!abstract] Role
> The Classifier reads the raw exception event from session state and returns a structured classification: type, subtype, severity, confidence, and key facts. It's the first specialist the Coordinator delegates to, and its output drives downstream decisions (including whether the Impact Agent gets called).

## Framework & Tech Stack

| Layer | Choice |
|-------|--------|
| Agent framework | Google ADK `LlmAgent` |
| LLM | Gemini 2.5 Flash |
| Classification approach | Few-shot (3 examples) |
| Tool pattern | Hybrid lazy tools (LLM decides when to call) |
| Output validation | Guardrails AI (hybrid: LLM reasons + validator enforces severity matrix) |
| Prompt format | Hybrid Markdown + XML delimiters (matches Coordinator) |

## Hierarchical Taxonomy (6 Types + 18 Subtypes)

```yaml
carrier_capacity_failure:
  - vehicle_breakdown_in_transit
  - driver_unavailable
  - capacity_exceeded

route_disruption:
  - road_closure
  - accident_on_route
  - traffic_jam_severe

regulatory_compliance:   # Rule C auto-escalates Impact
  - eway_bill_issue
  - gst_noncompliance
  - customs_hold
  - documentation_missing

customer_escalation:
  - wrong_delivery
  - delay_complaint
  - damage_claim
  - service_quality_complaint

external_disruption:
  - weather_event
  - port_delay
  - festival_demand_spike
  - labor_strike

safety_incident:   # Rule B triggers immediate human escalation
  - driver_injury
  - vehicle_accident
  - threat_or_security
  - hazmat_incident
```

## Tools (All 4 Tier 1 Tools)

### Tool 1: `translate_text`
```python
async def translate_text(text: str, source_lang: str, target_lang: str = "en") -> str:
    """
    Translates text from Hindi/Hinglish to English (or other pairs).
    Called when source_channel is voice/text in non-English.
    Uses Gemini's multilingual capability.
    """
```

### Tool 2: `check_safety_keywords`
```python
async def check_safety_keywords(text: str) -> dict:
    """
    Scans text in English, Hindi, Hinglish for safety keywords.
    Returns {detected: bool, keywords: list[str], severity: str}.
    Multi-language safety keyword scan — ALWAYS called first.
    If detected, triggers Rule B (escalation).

    Keywords include:
    - English: injury, accident, emergency, threat, hospital, blood, death
    - Hindi: durghatna, ghayal, khatra, aapatkaal, khoon, maut
    - Hinglish: accident ho gaya, injured hai, emergency hai, khatra hai
    """
```

### Tool 3: `get_festival_context`
```python
async def get_festival_context(date: str) -> dict:
    """
    Returns active Indian festivals within 7 days of given date.
    Supports: Diwali, Holi, Eid, Christmas, Ganesh Chaturthi,
    Durga Puja, Rakhi, Dussehra, Karwa Chauth, etc.
    Returns {active_festivals: list, days_until_nearest: int}.
    Uses festival_calendar.json static file for Tier 1.
    """
```

### Tool 4: `get_monsoon_status`
```python
async def get_monsoon_status(region: str) -> dict:
    """
    Returns current monsoon status for a given Indian region.
    Regions: western_ghats, east_coast, northern_plains, south_india, etc.
    Returns {is_active: bool, intensity: str, expected_end: str}.
    Uses monsoon_regions.json static file for Tier 1.
    For Tier 2, could integrate with IMD (India Meteorological Department) API.
    """
```

## Input Schema

Classifier reads `ExceptionEvent` from ADK session state (written by Coordinator):

```python
# Already defined in schemas/exception_event.py
class ExceptionEvent(BaseModel):
    event_id: str
    timestamp: datetime
    source_channel: str
    sender: dict
    raw_content: str
    original_language: Optional[str]
    english_translation: Optional[str]
    media_urls: list[str]
    metadata: dict
```

## Output Schema

```python
# schemas/classification.py
from pydantic import BaseModel, Field
from typing import Literal, Optional
from enum import Enum

class ExceptionType(str, Enum):
    carrier_capacity_failure = "carrier_capacity_failure"
    route_disruption = "route_disruption"
    regulatory_compliance = "regulatory_compliance"
    customer_escalation = "customer_escalation"
    external_disruption = "external_disruption"
    safety_incident = "safety_incident"

class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class ClassificationResult(BaseModel):
    exception_type: ExceptionType
    subtype: str  # Must match valid subtypes for the chosen type
    severity: Severity
    urgency_hours: Optional[int] = Field(None, description="Estimated hours until situation becomes critical")
    confidence: float = Field(..., ge=0.0, le=1.0)

    key_facts: dict = Field(..., description="Structured facts extracted from raw content")
    # e.g., {"location": "NH-48, Lonavala, KM 72", "vehicle_id": "MH-04-XX-1234"}

    reasoning: str = Field(..., description="1-3 sentences explaining the classification")
    requires_human_approval: bool = False
    tools_used: list[str] = Field(default_factory=list)

    # Rule B trigger (populated if safety_incident detected)
    safety_escalation: Optional[dict] = None
```

## Severity Matrix (Validator Layer — Relative Thresholds)

**Design principle:** Minimal hardcoded rules. Let the LLM reason about most severity decisions from context (deadlines, customer type, business impact). The validator ONLY enforces safety-critical hard rules and relative financial thresholds.

```python
# guardrails/classifier_validators.py

SEVERITY_RULES = [
    # (condition, minimum_severity, reasoning)

    # Rule 1: Safety is non-negotiable (Rule B from delegation rules)
    (
        lambda c, ctx: c.exception_type == "safety_incident",
        "CRITICAL",
        "Safety incidents are always CRITICAL"
    ),

    # Rule 2: Regulatory compliance auto-escalate (Rule C from delegation rules)
    (
        lambda c, ctx: c.exception_type == "regulatory_compliance"
                       and c.subtype in ["customs_hold", "eway_bill_issue", "gst_noncompliance"],
        "HIGH",
        "Regulatory compliance issues have cascading legal risk"
    ),

    # Rule 3: Relative financial threshold (5% of company daily revenue)
    (
        lambda c, ctx: (
            c.key_facts.get("value_at_risk_inr", 0) > 0
            and ctx.get("company_avg_daily_revenue_inr", 0) > 0
            and c.key_facts.get("value_at_risk_inr", 0) > 0.05 * ctx["company_avg_daily_revenue_inr"]
        ),
        "HIGH",
        "Value at risk exceeds 5% of company's daily revenue"
    ),

    # NOTE: Deadline-based severity is NOT hardcoded here.
    # The LLM is trusted to reason about deadlines from context
    # (customer tier, product type, market context, festival urgency)
    # because Indian 3PL reality has too much variance for hardcoded
    # deadline thresholds to work reliably across customer types.
]

def validate_severity(
    classification: ClassificationResult,
    company_context: dict,
) -> ClassificationResult:
    """
    Validates LLM's severity against minimal rule matrix.
    Rules can only ESCALATE severity, never downgrade.

    The LLM handles most severity reasoning; this validator only
    enforces safety, regulatory, and relative financial hard floors.
    """
    severity_order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    required_min = "LOW"
    escalation_reasons = []

    for condition, min_sev, reasoning in SEVERITY_RULES:
        if condition(classification, company_context):
            if severity_order[min_sev] > severity_order[required_min]:
                required_min = min_sev
                escalation_reasons.append(reasoning)

    # Escalate if LLM under-classified
    if severity_order[classification.severity] < severity_order[required_min]:
        original = classification.severity
        classification.severity = required_min
        classification.reasoning += (
            f" [Validator escalated from {original} to {required_min}: "
            f"{'; '.join(escalation_reasons)}]"
        )

    return classification
```

**Key design changes (from initial draft):**

1. **Removed hardcoded deadline thresholds (24hr/48hr/72hr)** — the LLM reasons about deadlines from context because Indian 3PL customer variety (D2C campaigns vs B2B manufacturing vs e-commerce) makes hardcoded rules brittle.

2. **Value-at-risk threshold is now RELATIVE (5% of avg_daily_revenue)** instead of absolute (₹10,00,000). This scales automatically with company size and matches the reality that the same ₹5L shipment is a crisis for a small 3PL and routine for a larger one.

3. **Validator takes `company_context` as input** — this creates a dependency: the company's avg_daily_revenue must be available via Supermemory before classification runs. Needs to be injected into session state by Coordinator middleware.

## Required Company Context Fields (for Validator)

The following fields must be in the company profile stored in Supermemory:

```python
# Added to company context schema in Coordinator spec
{
    "company_avg_daily_revenue_inr": 2_500_000,  # ~₹25L daily = ~₹75Cr annual
    # ... other existing fields from Section 4 of User Context Schema
}
```

If `company_avg_daily_revenue_inr` is not set, Rule 3 is skipped (LLM's severity is trusted).

## Classifier Instruction Prompt (Hybrid Format)

```markdown
# Classifier Agent — System Instructions

## Role
You are a specialist Classifier Agent for the Exception Triage Module.
You classify supply chain exception events for small 3PLs operating
in India. You receive raw exception events and return structured
classifications including type, subtype, severity, and key facts.

## Architectural Rules
1. You do NOT make resolution decisions. You only classify.
2. You do NOT assess impact. That's the Impact Agent's job.
3. You must use ONE of the predefined exception types and subtypes.
4. You must cite evidence from the raw content for every classification.

## Workflow
1. ALWAYS call `check_safety_keywords(raw_content)` FIRST
   - If safety detected: set type=safety_incident, severity=CRITICAL,
     and populate safety_escalation. STOP here.
2. If source_channel is whatsapp_voice/phone/non-English text:
   call `translate_text` if Gemini didn't already translate.
3. If the exception mentions time-sensitive context: call
   `get_festival_context(current_date)` to understand cultural urgency.
4. If the exception mentions weather/route disruption: call
   `get_monsoon_status(region)` to understand environmental context.
5. Classify: assign type + subtype from the taxonomy.
6. Assess severity using the severity heuristics below.
7. Extract key_facts (location, vehicle_id, deadline, customer_tier, etc.).
8. Provide concise reasoning (1-3 sentences).

## Taxonomy
<taxonomy>
carrier_capacity_failure:
  - vehicle_breakdown_in_transit
  - driver_unavailable
  - capacity_exceeded
route_disruption:
  - road_closure
  - accident_on_route
  - traffic_jam_severe
regulatory_compliance:
  - eway_bill_issue
  - gst_noncompliance
  - customs_hold
  - documentation_missing
customer_escalation:
  - wrong_delivery
  - delay_complaint
  - damage_claim
  - service_quality_complaint
external_disruption:
  - weather_event
  - port_delay
  - festival_demand_spike
  - labor_strike
safety_incident:
  - driver_injury
  - vehicle_accident
  - threat_or_security
  - hazmat_incident
</taxonomy>

## Severity Heuristics
- CRITICAL: Safety involved OR deadline < 24hr for high-value/public customer
            OR systemic multi-shipment disruption
- HIGH: Deadline < 48hr for customer-facing shipment
        OR value at risk > ₹10,00,000
        OR regulatory compliance issue (eway_bill, customs)
- MEDIUM: Deadline < 72hr OR any customer-facing impact
- LOW: Internal issue with buffer time, no customer-facing impact

Note: A validator will check your severity against a rule matrix
and escalate if you under-classified. You cannot be "too cautious,"
but you can be penalized for being too optimistic.

## Output Format
Return a valid ClassificationResult JSON matching the schema.
All fields are required except urgency_hours and safety_escalation.
confidence must be a float between 0.0 and 1.0.

## Examples
<few_shot_examples>
[Examples 1, 2, 3 — see Few-Shot Examples section below]
</few_shot_examples>
```

## Few-Shot Examples (3)

### Example 1: NH-48 Truck Breakdown (CRITICAL)

**Input:**
```json
{
  "event_id": "evt_001",
  "source_channel": "whatsapp_voice",
  "sender": {"name": "Ramesh Kumar", "role": "driver", "vehicle_id": "MH-04-XX-1234"},
  "raw_content": "Priya madam, namaste. Truck mein problem ho gaya hai. NH-48 pe, Lonavala ke paas, kilometre marker 72. Engine overheat ho gaya, smoke bhi aa raha tha. Maine roadside pe park kar diya hai. Mechanic ko phone kiya, woh bola 3-4 ghante lagega minimum.",
  "original_language": "hinglish"
}
```

**Expected tool calls:**
1. `check_safety_keywords(raw_content)` → `{detected: false}`
2. `translate_text(raw_content, "hinglish", "en")` → English translation
3. `get_festival_context("2026-04-10")` → `{active_festivals: [], days_until_nearest: 12}`

**Expected output:**
```json
{
  "exception_type": "carrier_capacity_failure",
  "subtype": "vehicle_breakdown_in_transit",
  "severity": "CRITICAL",
  "urgency_hours": 19,
  "confidence": 0.94,
  "key_facts": {
    "location": "NH-48, Lonavala, KM 72",
    "vehicle_id": "MH-04-XX-1234",
    "driver_name": "Ramesh Kumar",
    "estimated_resolution_hours": 4,
    "driver_status": "safe, roadside",
    "communication_channel": "whatsapp_voice",
    "original_language": "hinglish"
  },
  "reasoning": "Vehicle breakdown with shipments in transit. Mechanic ETA is 3-4 hours minimum. Driver is safe but truck is immobilized. Severity determined by urgency of downstream customer deadlines.",
  "requires_human_approval": false,
  "tools_used": ["check_safety_keywords", "translate_text", "get_festival_context"]
}
```

### Example 2: Delayed Shipment Complaint (MEDIUM)

**Input:**
```json
{
  "event_id": "evt_002",
  "source_channel": "email",
  "sender": {"name": "Rajesh Sharma", "role": "customer", "company": "GreenLeaf Organics"},
  "raw_content": "Hi, my order SHP-2024-5821 was supposed to arrive yesterday but tracking still shows 'in transit'. Can you give me an update? We need these within 3 days for our Saturday farmers market.",
  "original_language": "en"
}
```

**Expected output:**
```json
{
  "exception_type": "customer_escalation",
  "subtype": "delay_complaint",
  "severity": "MEDIUM",
  "urgency_hours": 72,
  "confidence": 0.88,
  "key_facts": {
    "customer_name": "GreenLeaf Organics",
    "shipment_id": "SHP-2024-5821",
    "deadline": "Saturday farmers market",
    "deadline_hours": 72,
    "customer_facing": true,
    "customer_tier": "standard"
  },
  "reasoning": "Customer delay complaint with 3-day buffer. Impacts a specific business event (farmers market) but not a CRITICAL public launch. Standard D2C customer.",
  "tools_used": ["check_safety_keywords"]
}
```

### Example 3: Driver Accident (Rule B Safety Trigger)

**Input:**
```json
{
  "event_id": "evt_003",
  "source_channel": "phone_call_transcript",
  "sender": {"name": "Dispatcher", "role": "internal"},
  "raw_content": "Emergency! Driver Sunil Verma called from highway. Hit-and-run accident near Surat toll plaza. He's injured, ambulance called. Our truck MH-12-CD-5678 has 6 shipments on board."
}
```

**Expected tool calls:**
1. `check_safety_keywords(raw_content)` → `{detected: true, keywords: ["injured", "accident", "ambulance"], severity: "CRITICAL"}`

**Expected output (STOPS after safety detection):**
```json
{
  "exception_type": "safety_incident",
  "subtype": "vehicle_accident",
  "severity": "CRITICAL",
  "urgency_hours": 0,
  "confidence": 0.99,
  "key_facts": {
    "driver_name": "Sunil Verma",
    "vehicle_id": "MH-12-CD-5678",
    "location": "Surat toll plaza",
    "incident_type": "hit_and_run",
    "injury_status": "injured, ambulance called"
  },
  "reasoning": "Safety incident with driver injury. Ambulance is already called. Escalating immediately per Rule B. No further classification work needed.",
  "requires_human_approval": true,
  "tools_used": ["check_safety_keywords"],
  "safety_escalation": {
    "trigger_reason": "driver_injury",
    "keywords_detected": ["injured", "accident", "ambulance"],
    "escalation_type": "immediate_human_safety"
  }
}
```

## Python Code Draft

```python
# agents/classifier.py
from google.adk.agents import LlmAgent
from pathlib import Path

from .tools import (
    translate_text,
    check_safety_keywords,
    get_festival_context,
    get_monsoon_status,
)

CLASSIFIER_INSTRUCTION = (
    Path(__file__).parent / "prompts" / "classifier.md"
).read_text()

classifier_agent = LlmAgent(
    name="ExceptionClassifier",
    model="gemini-2.5-flash",
    description=(
        "Classifies supply chain exception events by type, subtype, "
        "severity, and extracts key facts. Always checks safety keywords "
        "first. Uses translation, festival, and monsoon tools as needed."
    ),
    instruction=CLASSIFIER_INSTRUCTION,
    tools=[
        check_safety_keywords,
        translate_text,
        get_festival_context,
        get_monsoon_status,
    ],
    output_schema=ClassificationResult,  # ADK + Guardrails AI validation
)
```

## Open Decision: Severity Matrix Thresholds

The numbers in the severity matrix (₹10,00,000 value, 24hr, 48hr, 72hr cutoffs) are my guesses. These need validation from Indian 3PL domain knowledge. See open question in brainstorming.

## Cross-References

- [[Supply-Chain-Demo-Scenario-Tier1]] — The NH-48 scenario that's Example 1
- [[Supply-Chain-Agent-Spec-Coordinator]] — How Coordinator delegates to this Classifier
- [[Supply-Chain-Research-Sources]] — Research citations for classification best practices

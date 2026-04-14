---
title: "Agent Spec: Impact Agent (Tier 1)"
type: deep-dive
domains: [supply-chain, agent-design, hackathon]
last_updated: 2026-04-10
status: active
confidence: high
sources: ["[[Supply-Chain-Demo-Scenario-Tier1]]", "[[Supply-Chain-Agent-Spec-Coordinator]]", "[[Supply-Chain-Agent-Spec-Classifier]]", "[[Supply-Chain-Research-Sources]]"]
---

# Agent Spec: Impact Agent (Tier 1)

> [!abstract] Role
> The Impact Agent reads the Classification from session state and answers: "What does this actually affect?" It identifies affected shipments, calculates total impact using LLM-reasoned dynamic weights, orders them by priority, and flags D2C reputation risks. For our NH-48 scenario, it returns 4 affected shipments with BlushBox prioritized first due to the 19-hour campaign deadline.

## Framework & Tech Stack

| Layer | Choice |
|-------|--------|
| Agent framework | Google ADK `LlmAgent` |
| LLM | Gemini 2.5 Flash |
| Data source (live) | Firestore via tools |
| Data source (memory) | Supermemory via tools |
| Impact calculation | LLM-reasoned dynamic weights |
| Priority ordering | LLM-reasoned + validator |
| D2C reputation detection | Firestore metadata flag + LLM fallback |
| Prompt format | Hybrid Markdown + XML (matches Coordinator/Classifier) |

## Tools (Hybrid: Firestore live data + Supermemory memory)

### Firestore Tools (live operational data)

```python
async def get_active_shipments_by_vehicle(vehicle_id: str) -> list[Shipment]:
    """
    Returns all shipments currently assigned to a vehicle (status='in_transit').
    Used when exception is about a specific vehicle (e.g., truck breakdown).
    """

async def get_active_shipments_by_route(route_id: str) -> list[Shipment]:
    """
    Returns all shipments on a specific route or route segment.
    Used for route disruptions affecting multiple vehicles.
    """

async def get_active_shipments_by_region(region: str) -> list[Shipment]:
    """
    Returns all shipments within a geographic region.
    Used for weather events, port delays, labor strikes.
    """

async def get_shipment_details(shipment_id: str) -> ShipmentDetails:
    """
    Returns full shipment record including customer info, SLA terms,
    penalty clauses, public_facing_deadline flag, and deadline.
    """

async def get_customer_profile(customer_id: str) -> CustomerProfile:
    """
    Returns customer tier, SLA terms, churn risk score,
    relationship value, and historical reliability metrics.
    """
```

### Supermemory Tools (memory/patterns)

```python
async def lookup_customer_exception_history(
    customer_id: str,
    limit: int = 5,
) -> list[PastException]:
    """
    Returns the last N exceptions involving this customer.
    Helps LLM reason about:
    - Is this customer used to delays? (lower churn risk)
    - Have we missed deadlines with them before? (higher churn risk)
    - What resolutions worked for similar past exceptions?
    """

async def lookup_similar_past_exceptions(
    exception_context: str,
    limit: int = 3,
) -> list[PastException]:
    """
    Semantic search for similar past exceptions via Supermemory.
    Returns full context + how they were resolved + outcome.
    Helps LLM calibrate impact based on real precedents.
    """
```

## Input (from Session State)

Impact Agent reads from ADK session state:
- `exception_event: ExceptionEvent` (original raw event)
- `classification: ClassificationResult` (from Classifier)
- `user_context: dict` (injected by Coordinator middleware)
- `company_context: dict` (injected by Coordinator middleware)

## Output Schema

```python
# schemas/impact.py
from pydantic import BaseModel, Field
from typing import Literal, Optional
from decimal import Decimal

class ShipmentImpact(BaseModel):
    shipment_id: str
    customer_id: str
    customer_name: str
    customer_tier: Literal["high_value", "repeat_standard", "new", "b2b_enterprise"]
    customer_type: Literal["d2c", "b2b", "marketplace"]

    product_description: str
    value_inr: int
    destination: str

    deadline: str  # ISO timestamp
    hours_until_deadline: float

    # Risk assessments
    sla_breach_risk: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    churn_risk: Literal["LOW", "MEDIUM", "HIGH"]
    penalty_amount_inr: Optional[int] = None

    # Rule E: Reputation risk flag
    public_facing_deadline: bool = False
    reputation_risk_note: Optional[str] = None  # e.g., "Influencer campaign launch"
    reputation_risk_source: Optional[Literal["metadata_flag", "llm_inference"]] = None

    special_notes: Optional[str] = None


class ImpactResult(BaseModel):
    event_id: str
    affected_shipments: list[ShipmentImpact]

    # Impact totals
    total_value_at_risk_inr: int
    total_penalty_exposure_inr: int
    estimated_churn_impact_inr: Optional[int] = None

    # Priority
    critical_path_shipment_id: str  # The one that MUST be saved first
    recommended_priority_order: list[str]  # shipment_ids in priority order
    priority_reasoning: str  # LLM's explanation

    # Dynamic weights used (transparency)
    impact_weights_used: dict = Field(
        ...,
        description="The weights LLM chose for (value, penalty, churn) and why"
    )

    # Rule E flags
    has_reputation_risks: bool = False
    reputation_risk_shipments: list[str] = Field(default_factory=list)

    # Tools called
    tools_used: list[str] = Field(default_factory=list)

    # Narrative for Coordinator
    summary: str  # 2-3 sentences for the Coordinator to synthesize
```

## Instruction Prompt (Hybrid Format)

```markdown
# Impact Agent — System Instructions

## Role
You are a specialist Impact Agent for the Exception Triage Module.
After the Classifier has determined what kind of exception this is,
your job is to answer: "What does this actually affect, and what
should we prioritize saving first?"

## Architectural Rules
1. You do NOT classify exceptions. That's the Classifier's job.
2. You do NOT propose resolutions. That's the Resolution Agent (Tier 2).
3. You MUST base impact calculations on real Firestore data, not
   fabricated numbers.
4. You MUST cite evidence for every priority decision.

## Workflow
1. Read the classification from session state.
2. Identify the scope of impact from the exception context:
   - If vehicle-specific: call `get_active_shipments_by_vehicle`
   - If route-specific: call `get_active_shipments_by_route`
   - If region-specific: call `get_active_shipments_by_region`
3. For each affected shipment, get full details via `get_shipment_details`.
4. For each unique customer, get their profile via `get_customer_profile`.
5. Optionally: call `lookup_customer_exception_history` for customers
   where churn risk assessment would benefit from past patterns.
6. Reason about impact using LLM-reasoned dynamic weights (see below).
7. Order shipments by priority using LLM reasoning + hard rules.
8. Flag any D2C shipments with public-facing deadlines (Rule E).
9. Return structured ImpactResult with full reasoning.

## Impact Calculation — LLM-Reasoned Dynamic Weights

Do NOT use hardcoded weights. Instead, for each exception, reason
about what matters most GIVEN THE CONTEXT:

- If the affected customer is a NEW customer → churn weight is high
  (first impression matters)
- If the affected customer has missed deadlines with us before →
  churn weight is higher (relationship is fragile)
- If the customer is B2B enterprise with long relationship → value
  weight dominates (single incident won't break relationship)
- If the customer is D2C with public campaign → reputation weight
  dominates (social media risk)
- If there are penalty clauses → penalty weight is high

State the weights you chose in `impact_weights_used` with reasoning:
```json
{
  "value_weight": 0.4,
  "penalty_weight": 0.2,
  "churn_weight": 0.4,
  "reasoning": "High churn weight because 2 of 4 customers are new to NimbleFreight; losing them first-impression hurts LTV more than the shipment value."
}
```

## Priority Ordering — LLM + Hard Rules

Propose priority based on:
1. Hard rule: Public-facing D2C deadlines (Rule E reputation risk)
   before B2B deadlines of similar urgency
2. Hard rule: Deadline < 24 hours always precedes deadline > 48 hours
3. LLM reasoning: Within similar urgency bands, reason about customer
   tier, relationship value, and special context (festivals, launches)

Include `priority_reasoning` explaining your decisions in 2-3 sentences.

## Rule E: Reputation Risk Detection
For each affected shipment:
1. Check `public_facing_deadline` flag from Firestore metadata (primary source)
2. If flag is not set, infer from `product_description` and customer notes:
   - Keywords suggesting public events: "launch", "campaign", "influencer",
     "festival", "sale", "opening", "event", "premiere", "debut"
3. If reputation risk detected (either source), set the shipment's
   `reputation_risk_note` and populate `reputation_risk_shipments` list.
4. Populate `reputation_risk_source` to indicate whether it came from
   metadata or LLM inference.

## Output Format
Return a valid ImpactResult JSON matching the schema.
Include all affected shipments, total calculations, priority order,
reputation risks, and a 2-3 sentence summary for the Coordinator.

## Examples
<few_shot_example>
[See Example 1 below — NH-48 scenario]
</few_shot_example>
```

## Few-Shot Example: NH-48 Scenario

### Input (from session state)

```json
{
  "exception_event": {
    "event_id": "evt_001",
    "sender": {"role": "driver", "vehicle_id": "MH-04-XX-1234"}
  },
  "classification": {
    "exception_type": "carrier_capacity_failure",
    "subtype": "vehicle_breakdown_in_transit",
    "severity": "CRITICAL",
    "key_facts": {
      "vehicle_id": "MH-04-XX-1234",
      "location": "NH-48, Lonavala, KM 72"
    }
  }
}
```

### Expected Tool Calls

1. `get_active_shipments_by_vehicle("MH-04-XX-1234")` → returns 4 shipments
2. `get_shipment_details("SHP-2024-4821")` → BlushBox details
3. `get_shipment_details("SHP-2024-4822")` → FitHaus details
4. `get_shipment_details("SHP-2024-4823")` → KraftHeaven details
5. `get_shipment_details("SHP-2024-4824")` → CoreCloud details
6. `get_customer_profile("cust_blushbox")` → high_value D2C
7. `get_customer_profile("cust_fithaus")` → repeat_standard D2C
8. `get_customer_profile("cust_kraftheaven")` → new D2C
9. `get_customer_profile("cust_corecloud")` → b2b_enterprise
10. (Optional) `lookup_customer_exception_history("cust_blushbox", 3)` → BlushBox past patterns

### Expected Output

```json
{
  "event_id": "evt_001",
  "affected_shipments": [
    {
      "shipment_id": "SHP-2024-4821",
      "customer_id": "cust_blushbox",
      "customer_name": "BlushBox Beauty",
      "customer_tier": "high_value",
      "customer_type": "d2c",
      "product_description": "200 units Monsoon Muse lipstick launch",
      "value_inr": 850000,
      "destination": "Pune warehouse",
      "deadline": "2026-04-11T09:00:00+05:30",
      "hours_until_deadline": 18.75,
      "sla_breach_risk": "CRITICAL",
      "churn_risk": "HIGH",
      "penalty_amount_inr": 150000,
      "public_facing_deadline": true,
      "reputation_risk_note": "Influencer campaign launches at 10 AM tomorrow — public social media deadline",
      "reputation_risk_source": "metadata_flag",
      "special_notes": "Top priority customer, LTV ₹50L+"
    },
    {
      "shipment_id": "SHP-2024-4823",
      "customer_id": "cust_kraftheaven",
      "customer_name": "KraftHeaven Home",
      "customer_tier": "new",
      "customer_type": "d2c",
      "product_description": "80 handcrafted brass lamps for Diwali display",
      "value_inr": 380000,
      "destination": "Pune boutique",
      "deadline": "2026-04-13T10:00:00+05:30",
      "hours_until_deadline": 67.75,
      "sla_breach_risk": "MEDIUM",
      "churn_risk": "MEDIUM",
      "penalty_amount_inr": 0,
      "public_facing_deadline": true,
      "reputation_risk_note": "Diwali display deadline — cultural/seasonal significance",
      "reputation_risk_source": "llm_inference",
      "special_notes": "First order with new customer"
    },
    {
      "shipment_id": "SHP-2024-4824",
      "customer_id": "cust_corecloud",
      "customer_name": "CoreCloud Tech",
      "customer_tier": "b2b_enterprise",
      "customer_type": "b2b",
      "product_description": "12 server racks",
      "value_inr": 200000,
      "destination": "Pune enterprise client DC",
      "deadline": "2026-04-13T12:00:00+05:30",
      "hours_until_deadline": 69.75,
      "sla_breach_risk": "LOW",
      "churn_risk": "LOW",
      "penalty_amount_inr": 0,
      "public_facing_deadline": false,
      "special_notes": "Install coordination dependency with customer IT team"
    },
    {
      "shipment_id": "SHP-2024-4822",
      "customer_id": "cust_fithaus",
      "customer_name": "FitHaus Nutrition",
      "customer_tier": "repeat_standard",
      "customer_type": "d2c",
      "product_description": "150 protein boxes (routine replenishment)",
      "value_inr": 420000,
      "destination": "Pune warehouse",
      "deadline": "2026-04-12T20:00:00+05:30",
      "hours_until_deadline": 53.75,
      "sla_breach_risk": "LOW",
      "churn_risk": "LOW",
      "penalty_amount_inr": 0,
      "public_facing_deadline": false
    }
  ],
  "total_value_at_risk_inr": 1850000,
  "total_penalty_exposure_inr": 150000,
  "estimated_churn_impact_inr": 500000,
  "critical_path_shipment_id": "SHP-2024-4821",
  "recommended_priority_order": [
    "SHP-2024-4821",
    "SHP-2024-4823",
    "SHP-2024-4824",
    "SHP-2024-4822"
  ],
  "priority_reasoning": "BlushBox (4821) is the critical path — 19hr public campaign deadline with high churn risk and ₹1.5L penalty. KraftHeaven (4823) second due to Diwali cultural significance and new-customer first-impression risk. CoreCloud (4824) third due to B2B enterprise install coordination. FitHaus (4822) last as routine replenishment with buffer.",
  "impact_weights_used": {
    "value_weight": 0.35,
    "penalty_weight": 0.20,
    "churn_weight": 0.45,
    "reasoning": "Higher churn weight because 2 of 4 customers are D2C brands where public-facing failures damage reputation beyond single-order value. BlushBox has ₹1.5L penalty clause which drives moderate penalty weight."
  },
  "has_reputation_risks": true,
  "reputation_risk_shipments": ["SHP-2024-4821", "SHP-2024-4823"],
  "tools_used": [
    "get_active_shipments_by_vehicle",
    "get_shipment_details",
    "get_customer_profile"
  ],
  "summary": "Truck breakdown affects 4 shipments worth ₹18,50,000, with BlushBox Beauty as the critical path (19hr campaign deadline, HIGH churn risk). KraftHeaven Diwali lamps have secondary reputation risk. CoreCloud and FitHaus have buffer time."
}
```

## Python Code Draft

```python
# agents/impact.py
from google.adk.agents import LlmAgent
from pathlib import Path

from .tools import (
    get_active_shipments_by_vehicle,
    get_active_shipments_by_route,
    get_active_shipments_by_region,
    get_shipment_details,
    get_customer_profile,
    lookup_customer_exception_history,
    lookup_similar_past_exceptions,
)
from schemas.impact import ImpactResult

IMPACT_INSTRUCTION = (
    Path(__file__).parent / "prompts" / "impact.md"
).read_text()

impact_agent = LlmAgent(
    name="ImpactAgent",
    model="gemini-2.5-flash",
    description=(
        "Assesses the operational, financial, and reputational impact "
        "of classified supply chain exceptions. Identifies affected "
        "shipments, calculates total value at risk using LLM-reasoned "
        "dynamic weights, and proposes priority order. Flags D2C "
        "reputation risks per Rule E."
    ),
    instruction=IMPACT_INSTRUCTION,
    tools=[
        get_active_shipments_by_vehicle,
        get_active_shipments_by_route,
        get_active_shipments_by_region,
        get_shipment_details,
        get_customer_profile,
        lookup_customer_exception_history,
        lookup_similar_past_exceptions,
    ],
    output_schema=ImpactResult,  # Guardrails AI validation
)
```

## Firestore Schema Requirements (for Tool Implementation)

The Firestore schema must support these queries:

```javascript
// shipments collection
{
  shipment_id: "SHP-2024-4821",
  customer_id: "cust_blushbox",
  vehicle_id: "MH-04-XX-1234",
  route_id: "ROUTE-MUM-PUNE-01",
  region: "maharashtra_west",
  status: "in_transit",
  value_inr: 850000,
  deadline: Timestamp,
  public_facing_deadline: true,  // Rule E metadata flag
  reputation_risk_note: "Influencer campaign launches at 10 AM tomorrow",
  penalty_amount_inr: 150000,
  product_description: "200 units Monsoon Muse lipstick launch",
  destination: "Pune warehouse",
  special_notes: "Top priority customer",
  // ... other fields
}

// customers collection
{
  customer_id: "cust_blushbox",
  name: "BlushBox Beauty",
  customer_tier: "high_value",
  customer_type: "d2c",
  churn_risk_score: 0.7,  // 0-1 scale
  relationship_value_inr: 5000000,  // LTV
  sla_terms: { ... },
  // ... other fields
}
```

## Known Dependencies

1. **Coordinator must inject `company_avg_daily_revenue_inr`** into session state before calling Impact Agent (for Classifier's severity validator and any Impact-related relative thresholds).
2. **Firestore schema must have `public_facing_deadline` field** on shipments (Rule E primary source).
3. **Supermemory must be populated with past exception history** before `lookup_customer_exception_history` returns useful results. For Tier 1, this will be empty; LLM will just ignore the empty result.

## Cross-References

- [[Supply-Chain-Demo-Scenario-Tier1]] — The NH-48 scenario
- [[Supply-Chain-Agent-Spec-Coordinator]] — How Coordinator delegates to this
- [[Supply-Chain-Agent-Spec-Classifier]] — The Classifier whose output feeds Impact
- [[Supply-Chain-Research-Sources]] — Research citations

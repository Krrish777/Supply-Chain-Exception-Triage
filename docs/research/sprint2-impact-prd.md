---
title: "PRD: Impact Agent (Sprint 2)"
type: prd
domains: [supply-chain, agent-design, hackathon]
last_updated: 2026-04-16
status: proposed
confidence: high
sources:
  - "[[Supply-Chain-Agent-Spec-Impact]]"
  - "[[Supply-Chain-Agent-Spec-Coordinator]]"
  - "[[Supply-Chain-Firestore-Schema-Tier1]]"
  - "[[sprint1-classifier-research]]"
  - "[[gemini-structured-output-gotchas]]"
  - "[[adk-best-practices]]"
---

# PRD: Impact Agent — Sprint 2

> **SDLC gate:** This PRD must be approved before any implementation begins.

## 1. Purpose

The Classifier agent (Sprint 1) answers **"what kind of exception is this?"** The Impact
agent answers **"what does this actually affect?"** — affected shipments, financial
exposure, customer relationship risk, hub/facility congestion, and route cascade effects.

## 2. Scope — Full Ripple Analysis

Tier 1 Impact agent performs:

1. **Shipment impact** — identify all shipments affected by the exception
2. **Financial model** — deterministic cost calculation (penalties, rerouting, holding, opportunity)
3. **Customer relationship risk** — CRM-level churn assessment per affected customer
4. **Hub/facility capacity** — time-windowed congestion analysis at affected hubs
5. **Route cascade** — downstream leg impact for multi-leg corridor routes
6. **Priority ordering** — deterministic 5-factor scoring + LLM qualitative reasoning

## 3. Architecture

```
SequentialAgent("impact")
├── LlmAgent("impact_fetcher")
│   ├── tools: [get_affected_shipments, get_shipment_details,
│   │           get_customer_profile, get_route_and_hub_status,
│   │           calculate_financial_impact]
│   ├── output_key: "raw_impact_data"
│   ├── thinking_budget: 1024
│   ├── temperature: 0.0
│   └── Reads {triage:classification} from state
└── LlmAgent("impact_formatter")
    ├── output_schema: ImpactResult
    ├── output_key: "triage:impact"
    ├── thinking_budget: 1024
    ├── temperature: 0.0
    ├── include_contents: "none"
    └── before_model_callback: _clear_history
```

Same two-agent pattern as Classifier (Gemini 2.5 Flash forbids `output_schema` + tools).

## 4. Tool Design — 5 Tools

Research finding: Gemini Flash recommends 10–20 tools max for reliable selection.
5 tools is well within the safe zone. Merging the spec's 3 shipment-query tools
into 1 with a `scope_type` parameter reduces LLM routing decisions.

| # | Tool | I/O | Purpose |
|---|------|-----|---------|
| 1 | `get_affected_shipments` | Firestore async | Query shipments by `vehicle_id`, `route_id`, or `region`. Params: `scope_type`, `scope_value`. |
| 2 | `get_shipment_details` | Firestore async | Full shipment record + SLA terms + route segment. |
| 3 | `get_customer_profile` | Firestore async | CRM profile: tier, LTV, churn risk, escalation history, competitive threats. |
| 4 | `get_route_and_hub_status` | Firestore async | Multi-leg route + hub capacity/congestion at each node. |
| 5 | `calculate_financial_impact` | Pure compute | Deterministic financial breakdown. No I/O. |

### Tool-calling sequence (fetcher prompt prescribes explicitly)

1. Parse `{triage:classification}` → extract scope from `key_facts`
2. `get_affected_shipments(scope_type=..., scope_value=...)` → list of shipment summaries
3. For each shipment: `get_shipment_details(shipment_id=...)` → full details
4. For each unique customer: `get_customer_profile(customer_id=...)` → CRM data
5. `get_route_and_hub_status(route_id=...)` → cascade/hub data
6. For each shipment: `calculate_financial_impact(...)` → deterministic financials

### Dropped from spec (intentional)

- `lookup_customer_exception_history` — Supermemory stubbed until Sprint 4
- `lookup_similar_past_exceptions` — same reason

### Tool contracts

All tools follow existing patterns:
- Return: `{"status": "success"|"error"|"retry", "data": {...}}`
- Per-turn caching: `tool_context.state[f"cache:{key}"]`
- ToolContext as last param (runtime import, not TYPE_CHECKING)
- Pydantic at boundaries: validate Firestore docs on read, `model_dump(mode="json")` on return

## 5. Model Changes

### 5.1 Fix existing bugs in `models/impact.py`

| Bug | Fix |
|-----|-----|
| `extra="forbid"` on ShipmentImpact + ImpactResult | Remove — Gemini rejects `additionalProperties: false` in output_schema |
| `impact_weights_used: dict[str, Any]` | Remove entirely — weights move to post-processing callback |

### 5.2 New fields on `ShipmentImpact`

```python
rerouting_cost_inr: int = Field(0, ge=0)
holding_cost_inr: int = Field(0, ge=0)
opportunity_cost_inr: int = Field(0, ge=0)
current_route_leg: int | None = None     # which leg shipment is on
remaining_route_legs: int | None = None  # legs left to destination
```

### 5.3 New fields on `ImpactResult`

```python
total_financial_exposure_inr: int = Field(0, ge=0)  # all costs combined
cascade_risk_summary: str = ""          # LLM-written downstream effects
hub_congestion_risk: str | None = None  # which hubs are impacted
estimated_delay_hours: float = 0.0      # LLM's estimate from gathered data
```

Remove: `impact_weights_used: dict[str, Any]`

### 5.4 New model: `models/route.py` (internal, NOT output_schema)

```python
class RouteLeg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    leg_number: int = Field(..., ge=1)
    origin_hub: str
    destination_hub: str
    distance_km: float = Field(..., gt=0)
    estimated_hours: float = Field(..., gt=0)

class RouteDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    route_id: str = Field(..., min_length=1)
    corridor_name: str
    legs: list[RouteLeg]
    total_distance_km: float = Field(..., gt=0)

class HubCapacityWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    window_label: str          # "next_24h", "24_to_48h", "48_to_72h"
    utilization_pct: float     # 0-100
    pending_shipments: int

class HubStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hub_id: str = Field(..., min_length=1)
    hub_name: str
    city: str
    hub_type: Literal["major", "distribution", "transit", "regional"]
    capacity_containers_per_day: int
    current_utilization_pct: float
    congestion_level: Literal["LOW", "MODERATE", "HIGH", "CRITICAL"]
    time_windows: list[HubCapacityWindow]
```

### 5.5 New model: `models/financial.py` (internal, NOT output_schema)

```python
class FinancialBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shipment_value_inr: int = Field(..., ge=0)
    penalty_amount_inr: int = Field(0, ge=0)
    rerouting_cost_inr: int = Field(0, ge=0)
    holding_cost_inr: int = Field(0, ge=0)
    opportunity_cost_inr: int = Field(0, ge=0)
    total_exposure_inr: int = Field(..., ge=0)
    breakdown_notes: str = ""
```

## 6. Post-Processing Weights — Deterministic in `_after_agent`

Instead of LLM-produced `dict[str, Any]`, compute 5-factor priority scores
deterministically from the structured `ImpactResult` fields.

### 6.1 Factor weights

| Factor | Weight | Source |
|--------|--------|--------|
| value | 0.20 | `shipment.value_inr / max_value` (normalized) |
| penalty | 0.20 | `shipment.penalty_amount_inr / max_penalty` (normalized) |
| churn | 0.25 | Churn risk mapping + tier bonus (new=+0.2, high_value=+0.1) |
| facility_impact | 0.15 | Hub congestion: CRITICAL=1.0, HIGH=0.8, MODERATE=0.5, LOW=0.2 |
| cascade | 0.20 | `downstream_legs / total_legs` (normalized) |

### 6.2 Hard rule overrides (stacking)

- `public_facing_deadline == True` → score += 0.3 (Rule E)
- `hours_until_deadline < 24` → score += 0.2
- `hours_until_deadline < 6` → score += 0.4

### 6.3 Implementation

`_after_agent` callback:
1. Parse `triage:impact` from state
2. Compute scores per shipment
3. Re-sort `recommended_priority_order` by descending score
4. Store weights in `triage:impact_weights` (separate state key)
5. Write modified `triage:impact` back to state
6. Preserve LLM's `priority_reasoning` text alongside

## 7. Seed Data — Rich, Two-Tenant

### 7.1 Companies (2)

| Company | ID | Region Focus |
|---------|-----|-------------|
| SwiftLogix | `swiftlogix-001` | Maharashtra (existing) |
| NimbleFreight | `comp_nimblefreight` | Pan-India (new) |

### 7.2 Customers (7, full CRM profiles)

| Customer | Tier | Type | Company | LTV | Notable |
|----------|------|------|---------|-----|---------|
| `cust_blushbox` | high_value | d2c | SwiftLogix | ₹50L | Influencer campaigns, public deadlines |
| `cust_fithaus` | repeat_standard | d2c | SwiftLogix | ₹12L | Routine replenishment |
| `cust_kraftheaven` | new | d2c | SwiftLogix | ₹3L | First order, Diwali display |
| `cust_corecloud` | b2b_enterprise | b2b | SwiftLogix | ₹80L | Long relationship |
| `cust_mediquick` | b2b_enterprise | b2b | NimbleFreight | ₹120L | Pharma, cold chain |
| `cust_freshkart` | repeat_standard | marketplace | NimbleFreight | ₹25L | Grocery perishables |
| `cust_styleverse` | high_value | d2c | NimbleFreight | ₹40L | Competitor-threatened |

Each has: tier, contract terms, escalation history, delivery success rate,
relationship age, annual revenue, competitive threats, strategic importance,
default SLA terms, churn_risk_score, primary contact.

### 7.3 Routes (4 corridors)

| Route ID | Corridor | Legs | Distance |
|----------|----------|------|----------|
| `ROUTE-MUM-PUNE-01` | Mumbai-Pune Express | Mumbai → Lonavala → Pune | ~150km |
| `ROUTE-MUM-BLR-01` | Mumbai-Bangalore | Mumbai → Pune → Kolhapur → Hubli → Bangalore | ~980km |
| `ROUTE-DEL-JAI-AHM-01` | Delhi-Jaipur-Ahmedabad | Delhi → Jaipur → Udaipur → Ahmedabad | ~950km |
| `ROUTE-CHN-BLR-01` | Chennai-Bangalore | Chennai → Vellore → Bangalore | ~350km |

### 7.4 Hubs (8 facilities)

| Hub | City | Type | Capacity |
|-----|------|------|----------|
| `hub_mumbai` | Mumbai | Major | 500/day |
| `hub_pune` | Pune | Distribution | 200/day |
| `hub_bangalore` | Bangalore | Distribution | 300/day |
| `hub_delhi` | Delhi | Major | 600/day |
| `hub_jaipur` | Jaipur | Transit | 150/day |
| `hub_ahmedabad` | Ahmedabad | Regional | 250/day |
| `hub_chennai` | Chennai | Regional | 250/day |
| `hub_kolhapur` | Kolhapur | Transit | 80/day |

Each has time-windowed capacity: `next_24h`, `24_to_48h`, `48_to_72h`.

### 7.5 Shipments (~25)

**SwiftLogix (~10):**
- Group 1: NH-48 truck MH-04-XX-1234 — 4 shipments (linked to classifier exceptions)
- Group 2: Mumbai-Bangalore MH-04-YY-5678 — 3 shipments
- Group 3: Other in-transit — 3 shipments (noise/negatives)

**NimbleFreight (~15):**
- Group 4: Delhi-Ahmedabad DL-01-AA-3456 — 3 shipments
- Group 5: Chennai-Bangalore TN-09-CC-1234 — 3 shipments
- Group 6: Delivered/inactive — 6 shipments (negatives)

### 7.6 Financial heuristics

| Cost Type | Formula | Source |
|-----------|---------|--------|
| SLA Penalty | `min(penalty_per_hour * delay_hours, max_penalty)` | Customer SLA terms |
| Rerouting | `distance_km * ₹15/km` | Industry heuristic |
| Holding | `days * ₹500/day * containers` | Industry heuristic |
| Opportunity | `customer_ltv * churn_risk * 0.10` | 10% of LTV × churn probability |

These are Tier 1 demo estimates. Tier 2 moves to per-company Firestore config.

## 8. Callbacks

| Callback | Placed on | Purpose |
|----------|-----------|---------|
| `_before_agent` | SequentialAgent | Perf timer (`temp:impact:start_perf_ns`) |
| `_after_model` | Both fetcher + formatter | Token usage accumulation |
| `_clear_history` | Formatter `before_model` | `llm_request.contents = []` |
| `_after_agent` | SequentialAgent | 5-factor weight computation, priority re-sort, reputation risk validation, `log_agent_invocation` |

## 9. State Keys

| Key | Set by | Purpose |
|-----|--------|---------|
| `triage:classification` | Classifier (read-only for Impact) | Classification result to parse |
| `raw_impact_data` | Impact fetcher | Intermediate: raw gathered data |
| `triage:impact` | Impact formatter + `_after_agent` | Final structured impact result |
| `triage:impact_weights` | `_after_agent` | Deterministic weight breakdown (not in output_schema) |
| `temp:impact:start_perf_ns` | `_before_agent` | Performance timer |
| `temp:impact:tokens_in` | `_after_model` | Cumulative input tokens |
| `temp:impact:tokens_out` | `_after_model` | Cumulative output tokens |
| `cache:shipment:{id}` | Tools | Per-turn Firestore cache |
| `cache:customer:{id}` | Tools | Per-turn Firestore cache |
| `cache:route:{id}` | Tools | Per-turn Firestore cache |

## 10. File Structure

### New files

```
src/supply_chain_triage/modules/triage/agents/impact/
├── __init__.py
├── agent.py                 # create_impact() → SequentialAgent
├── tools.py                 # 5 tools
├── schemas.py               # ImpactInput envelope
└── prompts/
    ├── system_fetcher.md    # Data gathering workflow
    └── system_formatter.md  # Synthesis + priority reasoning

src/supply_chain_triage/modules/triage/models/
├── route.py                 # RouteLeg, RouteDefinition, HubCapacityWindow, HubStatus
└── financial.py             # FinancialBreakdown

scripts/
├── seed_impact_demo.py      # Seed all Impact collections
└── seed/
    ├── shipments.json
    ├── customers.json
    ├── routes.json
    ├── hubs.json
    └── companies_nimblefreight.json

runners/impact_runner.py     # POST /api/v1/impact

tests/unit/modules/triage/agents/impact/
├── __init__.py
├── test_tools.py
└── test_callbacks.py

tests/unit/modules/triage/models/
├── test_route.py
└── test_financial.py
```

### Modified files

```
src/supply_chain_triage/modules/triage/models/impact.py    # Bug fixes + new fields
src/supply_chain_triage/modules/triage/models/__init__.py  # New exports
tests/unit/modules/triage/models/test_impact.py            # Adapt to new schema
```

## 11. Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| 5 tools + ~13 tool calls/turn unreliable | Prescriptive fetcher prompt; `thinking_budget=1024` |
| `ImpactResult` with `list[ShipmentImpact]` is depth 2 | Keep ShipmentImpact flat, <30 properties total |
| Formatter needs both `{raw_impact_data}` AND `{triage:classification}` | Classifier populates state first; integration test validates |
| Financial heuristics are rough | Documented as Tier 1 estimates |
| Two-tenant seed doubles work | Reuse structure; script handles both |

## 12. Validation Scenarios

| # | Scenario | Expected behavior |
|---|----------|-------------------|
| 1 | NH-48 truck breakdown | 4 affected shipments, BlushBox critical path, ~₹18.5L value at risk |
| 2 | Monsoon flooding at JNPT | All Mumbai-origin shipments, hub congestion flagged |
| 3 | Customer escalation | CRM data shown, churn risk assessed |
| 4 | Regulatory customs hold | Compliance context, affected shipments identified |
| 5 | Minimal input | Graceful handling, low confidence |

## 13. Cross-References

- [[Supply-Chain-Agent-Spec-Impact]] — baseline spec (this PRD evolves it)
- [[Supply-Chain-Agent-Spec-Coordinator]] — how Coordinator delegates to Impact
- [[Supply-Chain-Firestore-Schema-Tier1]] — Firestore data model
- [[sprint1-classifier-research]] — Classifier decisions that Impact builds on
- [[gemini-structured-output-gotchas]] — Gemini bugs to avoid
- [[adk-best-practices]] — ADK patterns followed

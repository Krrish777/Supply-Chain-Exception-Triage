# Sprint 1 Classifier — Research Notes

> Date: 2026-04-16
> Purpose: Inform Sprint 1 Classifier PRD decisions based on web research + codebase analysis

## 1. Two-Agent Pattern (Fetcher + Formatter)

**Decision: Use `SequentialAgent(sub_agents=[fetcher, formatter])`**

ADK's `SequentialAgent` passes the same `InvocationContext` to each sub-agent — they share session state including the `temp:` namespace. The fetcher stores results via `output_key`, the formatter reads them via `{state_key}` template syntax.

- `output_schema` on an `LlmAgent` disables tool calling and delegation (confirmed in ADK cheatsheet and project rules)
- Gemini 2.5 Flash does NOT lift this restriction (Gemini 3.0 will)
- Canonical workaround: fetcher agent has tools + no output_schema; formatter agent has output_schema + no tools
- State flows automatically — no manual wiring needed

**Sources:**
- [ADK SequentialAgent docs](https://adk.dev/agents/workflow-agents/sequential-agents/)
- [Multi-agent patterns in ADK — Google Blog](https://developers.googleblog.com/developers-guide-to-multi-agent-patterns-in-adk/)
- [ADK Multi-agent systems](https://adk.dev/agents/multi-agents/)

---

## 2. Subtypes: Fixed Enum vs Free-Text

**Decision: Fixed enum per ExceptionType (constrained Literal)**

Research consensus: **enum over free text** for LLM classification.

> "By constraining the output to a predefined set of class names, you eliminate the need to parse or clean up free-form responses, which reduces the likelihood of errors and improves the reliability of the classification pipeline."

- `Literal` type works best across all models (more consistent than `StrEnum` for Gemini)
- Enum values should be short (Gemini structured-output reliability drops with long strings)
- Define 3-5 subtypes per ExceptionType for Tier 1

**Recommended subtypes per ExceptionType:**

| ExceptionType | Subtypes |
|---|---|
| carrier_capacity_failure | truck_breakdown, driver_shortage, capacity_overbook, vehicle_accident |
| route_disruption | road_closure, traffic_congestion, bridge_collapse, construction |
| regulatory_compliance | customs_hold, documentation_error, permit_violation, weight_limit |
| customer_escalation | delivery_complaint, sla_breach_threat, contract_termination, damage_claim |
| external_disruption | weather_flood, weather_storm, port_congestion, strike_bandh |
| safety_incident | driver_injury, cargo_spill, vehicle_fire, hazmat_exposure |

**Sources:**
- [Structuring Enums for LLM results](https://ohmeow.com/posts/2024-07-06-llms-and-enums.html)
- [Building Reliable Text Classification Pipeline](https://medium.com/data-science/building-a-reliable-text-classification-pipeline-with-llms-a-step-by-step-guide-87dc73205)
- [Structured Outputs in LLMs](https://www.leewayhertz.com/structured-outputs-in-llms/)

---

## 3. Severity Rules: Hybrid (LLM + Deterministic Overrides)

**Decision: LLM proposes severity, deterministic rules clamp invariants**

Industry approach: classify by severity × frequency × impact. Supply chain systems use dynamic threshold setting with ML models, but deterministic overrides for safety and regulatory compliance.

**Deterministic overrides (post-LLM clamp):**

| Rule | Condition | Minimum severity |
|---|---|---|
| Safety always critical | exception_type == "safety_incident" | CRITICAL |
| Regulatory floor | exception_type == "regulatory_compliance" | HIGH |
| High-value shipment | total_value_at_risk > ₹10L | HIGH |
| SLA breach imminent | urgency_hours < 4 | HIGH |
| Customer escalation + B2B enterprise | customer_tier == "b2b_enterprise" | HIGH |

**Escalation-only semantics:** severity can only go UP from LLM's initial assessment, never DOWN. Per guardrails.md §4 severity clamp pattern.

**Sources:**
- [Supply chain exception management — project44](https://www.project44.com/resources/what-is-an-exception-event-in-supply-chain-management/)
- [Exception management and why it matters](https://rtintel.com/what-is-supply-chain-exception-management-and-why-it-matters/)
- [Multi-criteria risk classification — Springer](https://link.springer.com/article/10.1007/s12597-021-00568-8)

---

## 4. Confidence Threshold for Human Escalation

**Decision: 0.7 threshold with calibration plan**

Research from ICLR 2025 shows LLMs are systematically overconfident. Static thresholds are suboptimal — dynamic calibration based on the model's actual calibration profile is best practice. However, for Tier 1 demo:

- **0.7** is the practical starting threshold (moderate — most classifications pass through)
- Safety incidents always require human approval regardless of confidence
- Calibration: track actual accuracy vs reported confidence in evalset, adjust threshold in Tier 2
- ICLR 2025 "Trust or Escalate" framework: cascade from small→large model when confidence is low

**For Tier 1 (demo):** `requires_human_approval = confidence < 0.7 or exception_type == "safety_incident"`

**Sources:**
- [Trust or Escalate: LLM Judges — ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/file/08dabd5345b37fffcbe335bd578b15a0-Paper-Conference.pdf)
- [Calibrating Confidence for Automated Assessment](https://arxiv.org/html/2603.29559)
- [Confidence Scores in LLMs](https://www.infrrd.ai/blog/confidence-scores-in-llms)

---

## 5. Tool Scope for Fetcher Agent

**Decision: Exception lookup + company context (2 tools)**

For Tier 1, the fetcher needs:
1. **`get_exception_event(event_id)`** — fetch ExceptionEvent from Firestore
2. **`get_company_profile(company_id)`** — fetch CompanyProfile (needed for severity rules: avg_daily_revenue, carrier list, regions)

Historical lookup (past similar exceptions) deferred to Tier 2 when memory layer is built.

Company context is essential because:
- Severity rules reference `avg_daily_revenue_inr` (Rule 3 in classification model)
- Regional context affects classification (e.g., monsoon patterns)
- `CompanyProfile.to_markdown()` is already built for prompt injection

---

## 6. Safety Escalation Patterns

**Decision: Keyword-based detection + LLM classification fallback**

Indian logistics safety context:
- Central Motor Vehicles Rules govern hazmat transport
- Driver must report hazmat accidents to nearest police station + vehicle owner
- Common safety incidents: driver injury/death, cargo spill, vehicle fire, hazmat exposure

**Keyword detection (deterministic, in `before_model_callback`):**
```
accident, injury, injured, death, killed, fatality, fire, spill, hazmat,
hazardous, medical emergency, collapsed, hospitalized, chemical leak,
tanker explosion, overturned
```

If keywords detected → set `safety_escalation` dict, force `severity=CRITICAL`, `requires_human_approval=True`.

LLM also classifies `safety_incident` as an ExceptionType — double coverage.

**Sources:**
- [Safety Incidents in Logistics — Falcony](https://blog.falcony.io/en/15-types-of-safety-incidents-in-logistics-and-transportation)
- [Hazardous Substances — Telangana Transport Dept](https://www.transport.telangana.gov.in/html/hazardous-substance.html)

---

## 7. Key Facts Extraction Structure

**Decision: Structured with defined keys per ExceptionType**

Research on supply chain NER shows extraction should produce structured triplets (source, relation, target). For our classifier:

**Common keys (all types):**
- `carrier_name`: str | null
- `route_origin`: str | null
- `route_destination`: str | null
- `affected_shipment_ids`: list[str]
- `estimated_delay_hours`: int | null
- `location`: str | null

**Type-specific keys:**

| ExceptionType | Additional keys |
|---|---|
| carrier_capacity_failure | `vehicle_id`, `driver_name`, `alternate_carrier` |
| route_disruption | `blocked_route`, `alternate_route`, `disruption_cause` |
| regulatory_compliance | `document_type`, `authority`, `deadline` |
| customer_escalation | `customer_name`, `complaint_type`, `sla_deadline` |
| external_disruption | `weather_type`, `affected_area`, `expected_duration_hours` |
| safety_incident | `incident_type`, `casualties`, `emergency_services_contacted` |

Prompt instructs LLM to fill available keys; null for unknown. Not enforced by schema (dict[str, Any]) but guided by examples.

**Sources:**
- [Supply Chain Network Extraction — arXiv](https://arxiv.org/html/2410.13051v1)
- [Entity Extraction — Google Cloud](https://cloud.google.com/discover/what-is-entity-extraction)

---

## 8. Thinking Budget

**Decision: `thinking_budget=0` for Tier 1, benchmark against 1024 in evalset**

Gemini 2.5 Flash thinking budget range: 1–24,576 tokens.

Research finding:
> "For tasks that don't need thinking (classification, summarization, simple Q&A), Flash with budget=0 and GPT-4o-mini are in the same ballpark."

Classification is a structured, fast task. `budget=0` disables thinking tokens → faster response, lower cost ($0.60/1M vs $1.50/1M for thinking tokens).

**Plan:**
- Start with `budget=0` in Tier 1 (fastest, cheapest)
- Run evalset with both `budget=0` and `budget=1024`
- If F1 delta > 0.05, switch to `budget=1024`
- The formatter (structured output agent) especially benefits from `budget=0` — it's just formatting

**Sources:**
- [Gemini 2.5 Flash Developer Guide](https://www.shareuhack.com/en/posts/gemini-2-5-flash-developer-guide-2026)
- [Vertex AI Thinking docs](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/thinking)
- [Gemini 2.5 Flash — OpenRouter](https://openrouter.ai/google/gemini-2.5-flash)

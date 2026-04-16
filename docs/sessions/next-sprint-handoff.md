# Next Session Handoff — Ready-to-Go Prompt

## Current state (as of 2026-04-16)

### What's done
- **Sprint 0**: Full infrastructure — rules, hooks, CI, logging, middleware, models, hello_world agent
- **Sprint 1**: Classifier agent — two-agent pattern, 2 Firestore tools, prompts, test endpoint, seed data, 24 unit tests passing, verified live in adk web with correct classification output

### What's NOT done yet
- Evalset (need capture-then-edit from adk web sessions)
- Impact agent (Sprint 2)
- Module Coordinator (Sprint 3)
- REST endpoint live-tested
- Firestore event_id Mode A tested
- All 7 test scenarios validated

---

## Your decisions (carry forward)

1. **Iterative dev** — demo-quality first, polish as we go
2. **English only** for Tier 1 — add Hindi/Hinglish in Tier 2
3. **Manual entry only** — no email/API channel parsing yet
4. **Classifier standalone** — no Coordinator wiring until Impact is ready
5. **Two-agent pattern** — fetcher (tools, no schema) + formatter (schema, no tools)
6. **Confidence 0.7** — below = human approval required
7. **Severity clamps** — safety→CRITICAL, regulatory→≥HIGH (deterministic, not LLM)
8. **15 evalset cases** — 6 happy + 4 edge + 3 safety + 2 adversarial
9. **No file-size hook** — removed from pre-commit (was causing problems)
10. **CI auto-fixes ruff** — lint/format auto-committed by GitHub Actions bot

---

## Architecture reference

```
SequentialAgent("classifier")
├── LlmAgent("classifier_fetcher")
│   ├── tools: [get_exception_event, get_company_profile]
│   ├��─ output_key: "raw_exception_data"
│   ├── thinking_budget: 1024
│   └── Two modes: raw text (Mode B) or event_id lookup (Mode A)
└── LlmAgent("classifier_formatter")
    ├── output_schema: ClassificationResult
    ├── output_key: "triage:classification"
    ├── thinking_budget: 1024
    ├── include_contents: "none"
    └── before_model_callback: _clear_history
```

**ClassificationResult** fields: exception_type (6 enums), subtype, severity (4 enums), urgency_hours, confidence, key_facts (list[KeyFact]), reasoning, requires_human_approval, tools_used, safety_escalation (SafetyEscalation | None)

---

## Critical gotchas (don't repeat these)

1. **No `dict[str, Any]`** in output_schema models — Gemini rejects `additionalProperties`
2. **No `extra="forbid"`** on output_schema models — same reason
3. **No colons in state keys** used in `{template}` instructions — ADK can't resolve them
4. **ToolContext must be runtime import** — not inside TYPE_CHECKING
5. **Callback params must match exactly** — `callback_context`, `llm_request`, `llm_response` — no underscore prefix
6. **Briefing data goes BEFORE examples** in formatter instruction — prevents hallucination
7. **`thinking_budget=0` degrades classification** �� use 1024 for formatter

---

## Tier 1 deadline: Apr 24 (8 days from Sprint 1 completion)

### Remaining work for Tier 1

| Priority | Task | Effort |
|----------|------|--------|
| **P0** | Validate Classifier with all 7 test scenarios | 1 hour (user) |
| **P0** | Build Impact agent (affected shipments, revenue at risk) | 1 sprint |
| **P0** | Build Module Coordinator (delegates to Classifier → Impact) | 1 sprint |
| **P0** | Simple web UI (inject exception → see triage result) | 1 sprint |
| **P1** | Create Classifier evalset (capture from adk web) | 1 hour |
| **P1** | Cloud Run deployment | 1 day |
| **P2** | Firestore seed data for Impact agent (shipments, customers) | 0.5 day |

### Sprint sequence suggestion

```
Sprint 2: Impact Agent
  - ShipmentImpact model already exists
  - Tools: query_affected_shipments, calculate_revenue_at_risk
  - Reads triage:classification from state
  - Two-agent pattern (same as classifier)

Sprint 3: Module Coordinator + Simple UI
  - Coordinator: receives exception, delegates Classifier → Impact
  - Returns TriageResult with both classification + impact
  - Simple HTML UI (not React — Tier 3)
  - Cloud Run deploy
```

---

## Ready-to-go prompt for next session

Copy this into the first message of your next Claude Code session:

```
Read these files for full context:
- .remember/remember.md (handoff buffer)
- docs/sessions/2026-04-16-sprint1-classifier.md (what was built + bugs found)
- docs/sessions/next-sprint-handoff.md (decisions + architecture + gotchas)
- docs/research/gemini-structured-output-gotchas.md (12 Gemini/ADK bugs)
- docs/research/adk-best-practices.md (patterns we follow)
- CLAUDE.md (project rules + SDLC cycle)
- docs/product_recap.md (product context)

CURRENT STATE:
- Sprint 0 (infra) + Sprint 1 (Classifier agent) are DONE and committed
- Classifier verified live in adk web — correct classifications produced
- 86 unit tests passing, ruff clean, mypy clean
- Firestore emulator seeded with 5 demo exceptions + 1 company

IMMEDIATE TODO:
1. Validate Classifier with remaining test scenarios (see test prompts in next-sprint-handoff.md)
2. Capture evalset from adk web sessions (capture-then-edit, 15 cases)

NEXT SPRINT: Impact Agent (Sprint 2)
- Per SDLC: Research → PRD → approval gate → Build → Test → Push
- Start with Research phase — review existing ImpactResult model, ShipmentImpact model
- Impact agent reads classification from state, queries Firestore for affected shipments
- Same two-agent pattern as Classifier (fetcher + formatter)

KEY CONSTRAINTS:
- Tier 1 deadline: Apr 24
- Iterative dev �� demo first, polish later
- English only for Tier 1
- See gotchas doc for Gemini/ADK bugs to avoid
```

---

## Test prompts to validate (not yet run)

### Test 1 — Truck breakdown (carrier_capacity_failure / MEDIUM)
```
BlueDart truck BD-MH12-4521 broke down on the Mumbai-Pune Expressway near Lonavala at 06:30 IST. Driver reports engine failure. 12 packages onboard for delivery today including 3 high-value B2B shipments for MegaMart. Mechanic ETA 3 hours.
```

### Test 2 — Customer escalation (customer_escalation / HIGH)
```
FINAL WARNING - This is our third escalation this month regarding delivery delays. Order #MM-2026-8834 was promised delivery by April 14th for our Diwali campaign pre-stock. It's April 16th and we still don't have the shipment. Our contract specifies Rs 50,000/day penalty for delays beyond 48 hours. We are seriously reconsidering our logistics partnership. Please resolve immediately or we will initiate contract termination proceedings.
```

### Test 3 — Ambiguous (route_disruption or external_disruption)
```
Truck delayed near Nashik, driver says road closed due to Maharashtra bandh. No ETA available. 8 shipments stuck.
```

### Test 4 — Minimal input (low confidence expected)
```
shipment late
```

### Test 5 — Regulatory (regulatory_compliance / MEDIUM→HIGH after clamp)
```
Customs hold at Chennai port for shipment CHN-2026-442. Missing phytosanitary certificate for agricultural goods consignment. FSSAI inspection has been triggered. Expected clearance delay 2-3 business days. No perishables in this particular shipment. Documentation team working on obtaining the certificate from the exporter.
```

### Test 6 — Monsoon (external_disruption / HIGH)
```
URGENT: Heavy monsoon flooding in Nhava Sheva port area since last night. Multiple container yards waterlogged. Access roads to JNPT blocked. Port operations suspended until further notice. Estimated 200+ containers affected across all operators. Water level still rising. Met department predicts continued heavy rain for 48 hours.
```

### Test 7 — Event ID lookup (Mode A, requires Firestore emulator running)
```
Classify exception with event_id: EXC-2026-0001
```

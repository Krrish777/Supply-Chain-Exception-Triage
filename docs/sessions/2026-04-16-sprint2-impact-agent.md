# 2026-04-16 — Sprint 2: Impact Agent

## What was built

Impact agent — two-agent pattern (fetcher + formatter) via SequentialAgent.
Reads classification from state, queries Firestore for affected shipments,
calculates financial exposure deterministically, assesses customer/hub/route
ripple effects, and returns structured ImpactResult with 5-factor priority scoring.

### Architecture

```
SequentialAgent("impact")
├── LlmAgent("impact_fetcher")
│   ├── tools: [get_affected_shipments, get_shipment_details,
│   │           get_customer_profile, get_route_and_hub_status,
│   │           calculate_financial_impact]
│   ├── output_key: "raw_impact_data"
│   └── thinking_budget: 1024
└── LlmAgent("impact_formatter")
    ├── output_schema: ImpactResult
    ├── output_key: "triage:impact"
    ├── thinking_budget: 1024
    └── before_model_callback: _clear_history
```

### Files created/modified

**Agent package:**
- `modules/triage/agents/impact/__init__.py`
- `modules/triage/agents/impact/agent.py` — `create_impact()` factory + 4 callbacks
- `modules/triage/agents/impact/tools.py` — 5 tools (4 async Firestore + 1 sync compute)
- `modules/triage/agents/impact/schemas.py` — `ImpactInput` envelope
- `modules/triage/agents/impact/prompts/system_fetcher.md` — 6-step tool-calling workflow
- `modules/triage/agents/impact/prompts/system_formatter.md` — synthesis + Rule E + few-shot

**Models (updated + new):**
- `modules/triage/models/impact.py` — fixed Gemini bugs, added financial/ripple fields
- `modules/triage/models/route.py` — RouteLeg, RouteDefinition, HubCapacityWindow, HubStatus
- `modules/triage/models/financial.py` — FinancialBreakdown

**Seed data:**
- `scripts/seed/customers.json` — 7 customers with full CRM profiles
- `scripts/seed/routes.json` — 4 Indian logistics corridors
- `scripts/seed/hubs.json` — 12 hub nodes with time-windowed capacity
- `scripts/seed/shipments.json` — 22 shipments across corridors
- `scripts/seed/companies_nimblefreight.json` — NimbleFreight company
- `scripts/seed_impact_demo.py` — seeder with --live and --collection flags

**Infrastructure:**
- `runners/impact_runner.py` — POST /api/v1/impact endpoint

**Tests:** 42 new (tools: 27, callbacks: 15), all passing. Total: 186 passing + 1 pre-existing failure.

## Key decisions

1. **5 tools** (down from spec's 7) — merged 3 shipment queries into 1 with `scope_type`; dropped 2 Supermemory tools (stubbed until Sprint 4)
2. **Post-processing weights** — 5-factor deterministic scoring in `_after_agent` callback instead of LLM-produced `dict[str, Any]` (Gemini compatibility)
3. **Two-tenant seed data** — SwiftLogix (Maharashtra) + NimbleFreight (pan-India) for multi-tenancy demo
4. **Hybrid financial model** — tools calculate deterministic costs, LLM adds qualitative context
5. **12 hubs** (expanded from original 8) — added 4 transit hubs for route referential integrity

## Bugs fixed

| Bug | Root cause | Fix |
|-----|-----------|-----|
| `extra="forbid"` on output_schema models | Gemini rejects `additionalProperties: false` | Removed from ShipmentImpact + ImpactResult |
| `impact_weights_used: dict[str, Any]` | Gemini rejects `additionalProperties` | Moved to post-processing callback |
| Missing transit hubs in seed data | Route legs referenced hubs not in collection | Added 4 transit hubs |

## Verification results

- **pytest**: 186 passed, 1 failed (pre-existing), 1 skipped
- **ruff**: All checks passed
- **mypy**: No issues in 44 source files
- **Coverage**: tools.py 98%, agent.py 91%, models 100%

## Open for next session

- Live test via `adk web` (requires Firestore emulator + seed data loaded)
- Evalset creation (capture-then-edit from adk web sessions)
- Sprint 3: Module Coordinator (delegates Classifier → Impact)
- The pre-existing test failure in test_classification.py should be fixed (dict vs list[KeyFact])

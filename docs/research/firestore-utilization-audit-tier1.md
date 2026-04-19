---
title: "Firestore Utilization Audit — Tier 1"
type: audit
domains: [supply-chain, firestore, multi-tenant, tier-1]
last_updated: 2026-04-18
status: active
confidence: high
sources:
  - "[[Supply-Chain-Firestore-Schema-Tier1]]"
  - "[[zettel-firestore-multi-tenant]]"
  - https://firebase.google.com/docs/firestore/best-practices
  - https://firebase.google.com/docs/firestore/security/rules-structure
  - https://firebase.google.com/docs/firestore/query-data/indexing
  - https://firebase.google.com/docs/firestore/query-data/index-overview
  - https://cloud.google.com/python/docs/reference/firestore/latest/google.cloud.firestore_v1.async_client.AsyncClient
  - https://firebase.google.com/docs/auth/admin/custom-claims
  - https://firebase.google.com/docs/rules/rules-and-auth
related:
  - docs/research/Supply-Chain-Firestore-Schema-Tier1.md
  - docs/research/zettel-firestore-multi-tenant.md
  - .claude/rules/firestore.md
  - .claude/rules/security.md
---

# Firestore Utilization Audit — Tier 1

> **Purpose.** A single, self-contained reference for the engineer building the Tier 1 Firestore foundation. Captures (a) what exists today in this repo, (b) the gaps against agent requirements + the authoritative schema, (c) the target collection layouts, rules, and indexes, (d) seed strategy, and (e) a concrete, file-by-file next-session task list. After reading this, no web search or code spelunking should be needed to execute.

---

## 1. Executive Summary

**Current utilization score: 55/100.**

We have a credible scaffolding: rules exist, indexes exist, seed JSON for the dense collections (`customers`, `routes`, `hubs`, `shipments`, `companies_nimblefreight`) is rich and internally consistent, `get_firestore_client()` is a DI chokepoint, and custom-claims discipline is in place. But five of the collections that the agents actively query fall outside rule coverage or seed coverage, the seed layer is fragmented across four overlapping scripts with no single idempotent entry point, and the audit-archive write path (`triage_results` + `audit_events`) — which the product needs for the dashboard history tab — does not exist yet.

### Top 5 gaps

1. **`routes` + `hubs` are unreachable by authenticated users** — Impact's `get_route_and_hub_status` tool reads them, but `infra/firestore.rules` has no matcher for either collection, so the explicit `match /{path=**}` catch-all denies every client read. Today this only works because the Admin SDK (used by tools in server context) bypasses rules; any client-side read (dashboard, Tier 3 frontend) breaks silently.
2. **Stub seed files for four static reference collections.** `scripts/seed/companies.json`, `scripts/seed/users.json`, `scripts/seed/festival_calendar.json`, `scripts/seed/monsoon_regions.json` are all 1-line `[]` stubs. `scripts/seed_firestore.py` is a dry-run shell that flags the first two as Sprint-2 work but was never wired. `scripts/seed_emulator.py` and `scripts/seed_impact_demo.py` both inline `companies.json` data at runtime, so the JSON-as-source-of-truth invariant is broken.
3. **No `triage_results` collection and no `audit_events` collection.** Every full-pipeline run today evaporates after the response returns — classification + impact are shaped by `TriageResult` in memory but never written anywhere. The user's dashboard history requirement and the `audit_event` helper contract in `.claude/rules/observability.md` §6 both depend on persistence that does not exist.
4. **Four overlapping seeder scripts with drift between them.** `seed_firestore.py` (Sprint-0 shell), `seed_emulator.py` (inlines some data, reads others), `seed_classifier_demo.py` (inlines exceptions + SwiftLogix), `seed_impact_demo.py` (reads JSON). Each picks a different subset and has its own emulator/prod handling. There is no single `scripts/seed_all.py` that idempotently seeds the full demo corpus.
5. **Index coverage is only for `shipments` + `exceptions`.** The five composite indexes listed for `customers`, `routes`, and `hubs` in the authoritative spec (`Supply-Chain-Firestore-Schema-Tier1.md`) never landed in `firestore.indexes.json`. In practice: `customers` has tier/type filters that will need indexes once the dashboard queries them; `routes` and `hubs` are keyed-read-only today and actually need zero indexes — we would be over-indexing if we added them speculatively.

### Top 3 strengths

1. **The multi-tenant anchor is correct.** Every tenant doc carries `company_id`, rules use `isCompanyMember(resource.data.company_id)` for reads + `incomingIsOwnCompany()` for writes (create-side isolation), custom claims are set server-side only via `scripts/set_custom_claims.py`. The three moving parts (data shape, token claim, rule) all agree. This is the hard part — it's right.
2. **Seed content quality is high where it exists.** `customers.json` (7 docs), `shipments.json` (25 docs, deliberately mixed active + delivered + negative-test noise), `routes.json` (4 real Indian corridors), `hubs.json` (12 hubs with 3-window capacity snapshots) are all well-shaped, reference-consistent (every `shipment.customer_id` resolves to a customer, every leg's `origin_hub`/`destination_hub` resolves to a hub), and mapped to the NH-48 flagship scenario. This is a deliberately-built corpus, not random sample data.
3. **`get_firestore_client()` is a proper DI chokepoint.** Singleton via `lru_cache`, emulator auto-detection via `FIRESTORE_EMULATOR_HOST`, exports the Settings field to the real env var before SDK construction (CR9), and is the *only* place in `core/` allowed to import `google.cloud.firestore`. Framework-swap-tolerant and test-friendly. Agents + tools never instantiate clients.

---

## 2. Current State Audit (collection-by-collection)

| Collection | Defined in rules? | Indexed? | Seeded? | Queried by | Doc shape source |
|---|---|---|---|---|---|
| `companies` | Yes — read by member, write denied (Admin SDK only) | No — keyed reads only | Partial — `companies_nimblefreight.json` (1 doc) + SwiftLogix inlined in 2 scripts; `companies.json` is `[]` stub | Classifier `get_company_profile` | `CompanyProfile` / `CustomerPortfolio` (`models/company_profile.py`) |
| `users` | Yes — `request.auth.uid == userId` only, write denied | No — keyed reads only | No — `users.json` is `[]` stub; not written anywhere | Not yet queried at runtime (Coordinator planning) | `UserContext` / `WorkingHours` (`models/user_context.py`) |
| `shipments` | Yes — full CRUD gated by `company_id` membership + create-side isolation | Yes — 5 composite indexes covering `vehicle_id`, `route_id`, `region`, `customer_id`, `status+deadline` | Yes — 25 docs in `shipments.json`, references resolve | Impact `get_affected_shipments` (query by scope), `get_shipment_details` (by ID) | inferred from seed JSON + `ShipmentImpact` consumer model |
| `customers` | Yes — full CRUD gated | No — authoritative spec lists `customer_tier` + `customer_type`, but no query in-code uses them yet | Yes — 7 docs in `customers.json`, split across both tenants | Impact `get_customer_profile` (by ID only today) | inferred from seed JSON; consumer `ShipmentImpact.customer_tier`/`customer_type` |
| `routes` | **NO — fails into `/{path=**}` catch-all deny** | No | Yes — 4 docs in `routes.json` | Impact `get_route_and_hub_status` (by ID) | `RouteDefinition` + `RouteLeg` (`models/route.py`) |
| `hubs` | **NO — fails into catch-all deny** | No | Yes — 12 docs in `hubs.json` | Impact `get_route_and_hub_status` (N gets by ID) | `HubStatus` + `HubCapacityWindow` (`models/route.py`) |
| `exceptions` | Yes — read by member, write denied (server-side only) | Yes — 4 composite indexes (created_at DESC, user_id+created_at, classification.exception_type, classification.severity) | Yes — 2 docs inlined in `seed_emulator.py`; 5 docs inlined in `seed_classifier_demo.py`; no seed JSON file | Classifier `get_exception_event` (by ID); Impact `get_exception_event` (by ID) | `ExceptionEvent` (`models/exception_event.py`) — intake shape only, not the extended audit-archive shape from `Supply-Chain-Firestore-Schema-Tier1.md` §256 |
| `festival_calendar` | Yes — auth read only, write denied | No | **No** — `festival_calendar.json` is `[]` stub | Not yet queried (Classifier tool deferred to Rule D) | Spec in `Supply-Chain-Firestore-Schema-Tier1.md` §333 |
| `monsoon_regions` | Yes — auth read only, write denied | No | **No** — `monsoon_regions.json` is `[]` stub | Not yet queried | Spec in `Supply-Chain-Firestore-Schema-Tier1.md` §358 |
| **`triage_results`** | **Does not exist** | — | — | Intended: every pipeline run writes one | To define (this doc §4) |
| **`audit_events`** | **Does not exist** | — | — | Intended: `audit_event()` helper fans out here for the dashboard history | To define (this doc §4) |

### Existing indexes (verbatim from `infra/firestore.indexes.json`)

All 9 composite indexes target `shipments` or `exceptions`. Every one is justified by a real query — no speculative indexes to reclaim. Verified query pathways:

- `shipments (company_id, vehicle_id, status)` — used by `get_affected_shipments(scope_type="vehicle_id", ...)` but note the tool queries `(status, vehicle_id)` with `company_id` implicit; we'll reconcile in §8.
- `shipments (company_id, route_id, status)` — `get_affected_shipments(scope_type="route_id", ...)`.
- `shipments (company_id, region, status)` — `get_affected_shipments(scope_type="region", ...)`.
- `shipments (company_id, customer_id, status)` — not yet used at runtime, reserved for dashboard "per-customer shipments" view.
- `shipments (company_id, status, deadline)` — not yet used at runtime, reserved for "urgent" queries.
- `exceptions (company_id, created_at DESC)` — reserved for history-tab pagination.
- `exceptions (company_id, user_id, created_at DESC)` — per-user history.
- `exceptions (company_id, classification.exception_type)` — analytics tile.
- `exceptions (company_id, classification.severity)` — analytics tile.

### Rule coverage gaps (verbatim test of `infra/firestore.rules` vs tool call sites)

| Tool | Collection accessed | Rule matcher hit? | Behavior for authenticated client read |
|---|---|---|---|
| `classifier.get_exception_event` | `exceptions/{id}` | Yes — `match /exceptions/{exceptionId}` | Allowed if `company_id` matches |
| `classifier.get_company_profile` | `companies/{id}` | Yes — `match /companies/{companyId}` | Allowed if `company_id` matches doc ID |
| `impact.get_exception_event` | `exceptions/{id}` | Yes | Same as classifier |
| `impact.get_affected_shipments` | `shipments` query | Yes — `match /shipments/{shipmentId}` | Allowed per-doc by `company_id` |
| `impact.get_shipment_details` | `shipments/{id}` | Yes | Allowed |
| `impact.get_customer_profile` | `customers/{id}` | Yes — `match /customers/{customerId}` | Allowed |
| `impact.get_route_and_hub_status` | `routes/{id}` + `hubs/{id}` | **NO — no matcher; catch-all denies** | **Denied unless Admin SDK bypass** |

### Seed script overlap matrix

|  | `seed_firestore.py` | `seed_emulator.py` | `seed_classifier_demo.py` | `seed_impact_demo.py` |
|---|---|---|---|---|
| `companies` (SwiftLogix) | Looks for JSON | **Inlined in Python** | **Inlined in Python** | — |
| `companies` (NimbleFreight) | Looks for JSON | Reads `companies_nimblefreight.json` | — | Reads `companies_nimblefreight.json` |
| `users` | Looks for JSON (empty) | — | — | — |
| `exceptions` | — | **Inlined in Python (2 docs)** | **Inlined in Python (5 docs)** | — |
| `customers` | — | Reads JSON | — | Reads JSON |
| `routes` | — | Reads JSON | — | Reads JSON |
| `hubs` | — | Reads JSON | — | Reads JSON |
| `shipments` | — | Reads JSON | — | Reads JSON |
| `festival_calendar` | Looks for JSON (empty) | — | — | — |
| `monsoon_regions` | Looks for JSON (empty) | — | — | — |
| Idempotent? | Dry-run only | `.set()` (idempotent) | `.set()` (idempotent) | `.set()` (idempotent) |
| Emulator-aware? | No (shell) | Forces emulator before import | Via `get_firestore_client()` | Via `get_firestore_client()` |
| Target | Nothing | Emulator only | Emulator or prod | Emulator or prod |
| Wipe mode? | No | No | No | No |

**Read:** four scripts, no single "seed everything" command, exceptions-data-of-record is inlined not JSON, and no option to wipe-then-seed for deterministic demo replays. Consolidation plan in §9.

---

## 3. Gap Analysis

### 3.1 Critical — rule gaps that break the product

**`routes` + `hubs` unreachable by clients.** Add explicit rules. Both are read-heavy reference data scoped per-tenant conceptually (tenant-shared logistics network) but not today marked with `company_id` in the seed JSON (`routes.json` and `hubs.json` have no `company_id` field). Two options:

1. **Treat as tenant-shared reference data** (current seed shape). Rule: authenticated-read only, server-side writes only. Analogous to `festival_calendar` / `monsoon_regions`. This is the pragmatic Tier 1 choice — no `company_id` migration required.
2. **Treat as tenant-private.** Would require adding `company_id` to every route + hub and filtering by membership. More correct long-term (a 3PL's corridor map is competitive IP) but overkill for Tier 1. Defer to Tier 2.

**Pick option 1 for Tier 1.** Spec in §7.

### 3.2 Critical — missing audit-archive path

**`triage_results` collection.** Every `/api/triage` run shapes a `TriageResult` in memory, emits an SSE stream to the client, and drops the result. Dashboard-history requires persistence. Define the collection (§4), write from the Coordinator's `after_agent_callback` (per-run, Admin SDK write path), index by `(company_id, created_at DESC)`. Retention decision still open (see §17).

**`audit_events` collection.** The `audit_event()` helper in `.claude/rules/observability.md` §6 emits structured logs — fine for Cloud Logging, but the dashboard can't pull audit history from Cloud Logging without BigQuery export. Add a Firestore mirror for the high-signal events (`agent_invoked`, `classification_result`, `escalation_triggered`, `permission_denied`) keyed by `correlation_id`. Cost: +1 write per event vs today's +0; acceptable per §14 cost model.

### 3.3 High — stub seed files

Each of the 4 stub files has a clear use and a deferred blocker:

| File | Status | Used by | Blocker / reason it's empty |
|---|---|---|---|
| `companies.json` | `[]` stub | `seed_firestore.py` loader (unwired), `seed_all.py` (proposed) | Content exists inlined in `seed_classifier_demo.py` (SwiftLogix) and in `companies_nimblefreight.json` — needs to be consolidated into one list |
| `users.json` | `[]` stub | `seed_firestore.py` loader, `seed_all.py` | Never-authored. Tier 1 has no user-facing writes yet; but `users/{uid}` will be read by the dashboard to render identity + preferences (required for ADK prompt injection per `UserContext.to_markdown()`) |
| `festival_calendar.json` | `[]` stub | Future Classifier `get_festival_context` tool (Rule D) | Tool itself deferred — but data should exist now so the collection is real before the rule is added |
| `monsoon_regions.json` | `[]` stub | Future Classifier `get_monsoon_status` tool (Rule D) | Same — data first, tool later |

Proposed contents in §10.

### 3.4 Medium — seeder consolidation

Four scripts → one `scripts/seed_all.py` + `scripts/seed/` as source of truth. The four existing scripts stay on disk for one more sprint as backward-compat shims, then delete. Detailed plan in §9.

### 3.5 Low — unused / missing indexes

**No action today on `customers`, `routes`, `hubs` indexes.** Every query today is by document ID or a composite that `shipments` already covers. Adding `(company_id, customer_tier)` or `(company_id, customer_type)` speculatively violates Firestore best practice — "Examine your most common queries and tailor your indexes to match the specific filters and sorts you use most often" ([Firebase best practices](https://firebase.google.com/docs/firestore/best-practices)). Add when the dashboard actually writes a filtered query.

**Add now:** indexes for `triage_results` + `audit_events` (both new collections). Detail in §8.

**Flag for review:** `shipments (company_id, customer_id, status)` and `shipments (company_id, status, deadline)` were added speculatively — they aren't used by any tool in this audit. Keep for the dashboard; revisit after Tier 1 ship.

---

## 4. Target Tier 1 Schema (document-shape definitions)

Reference existing Pydantic models where they exist; document enhancements inline. Every non-static document has `company_id` (tenant anchor) + `created_at` / `updated_at` (tz-aware).

### 4.1 `companies/{company_id}`

Maps to `CompanyProfile` (existing, in `models/company_profile.py`). **Enhancements proposed by user goal (c):** add escalation matrix, business-hours/holiday calendar, preferred language/communication style, SLA templates per customer tier. Full spec in §5.

```python
# Existing fields (do not change shape)
company_id: str                       # Firestore document ID
name: str
profile_summary: str
num_trucks: int                       # ge=0
num_employees: int                    # ge=0
regions_of_operation: list[str]
carriers: list[str]
customer_portfolio: CustomerPortfolio  # d2c_percentage, b2b_percentage, b2b_enterprise_percentage, top_customers
avg_daily_revenue_inr: int            # required for Classifier Rule 3 (5% threshold)
active: bool                          # default True

# NEW for Tier 1 (§5 spec)
escalation_matrix: list[EscalationContact]       # per-severity contact list
business_hours: BusinessHours                    # tz-aware operating window
holiday_calendar: list[Holiday]                  # company-specific observed holidays
preferred_language: Literal["english","hindi","hinglish"]
communication_style: CommunicationStyle          # tone, formality, channel prefs
sla_templates: list[SLATemplate]                 # per-customer-tier defaults
created_at: datetime                             # tz-aware
updated_at: datetime                             # tz-aware
```

### 4.2 `users/{uid}`

Doc ID **equals Firebase Auth `uid`** (enforced by rule: `request.auth.uid == userId`). Maps to `UserContext` today.

```python
user_id: str                  # Firestore doc ID = Firebase uid
company_id: str               # redundant with custom claim; stored for cross-reference
name: str
email: str
role: str                     # "Exception Coordinator", "Dispatcher", "Ops Manager"
experience_years: int         # ge=0
city: str
state: str
timezone: str                 # IANA, e.g. "Asia/Kolkata"
avg_daily_shipments: int      # ge=0
avg_daily_exceptions: int     # ge=0
busiest_days: list[str]
workload_classification: str  # "manageable" | "overloaded"
preferred_language: str       # user-level override of company default
tone: str                     # "concise" | "detailed" | "bullet_points"
formality: str                # "formal" | "casual"
notification_channels: list[str]
working_hours: WorkingHours   # start, end (HH:MM)
override_patterns: list[str]        # Tier 2+ populated
learned_priorities: dict[str, float] # numeric weights
created_at: datetime
last_active: datetime
```

Full §6 profile spec expands this with the "role" enum.

### 4.3 `shipments/{shipment_id}`

Shape is exactly what the seed `shipments.json` already produces — well-established and agent-consumed. Key fields, re-stated for index justification:

```python
shipment_id: str
company_id: str                # tenant anchor
customer_id: str               # FK → customers/{customer_id}
vehicle_id: str
route_id: str                  # FK → routes/{route_id}
region: str                    # denormalized from route for query efficiency
status: Literal["in_transit","delivered","delayed","exception"]
product_description: str
value_inr: int
weight_kg: float
origin: str
destination: str
deadline: datetime             # tz-aware
deadline_type: str             # "campaign_launch" | "standard_delivery" | ...
public_facing_deadline: bool   # Rule E (reputation risk) trigger
reputation_risk_note: str      # only when public_facing_deadline=True
sla_terms: {on_time_threshold_hours, penalty_per_hour_delayed_inr, max_penalty_inr, breach_triggers_refund}
penalty_amount_inr: int        # pre-computed max exposure
special_notes: str
customer_tier_snapshot: str    # denormalized at shipment creation
customer_type_snapshot: str    # denormalized at shipment creation
route_segment: {route_id, current_leg, total_legs, origin_hub, destination_hub, estimated_arrival}
created_at: datetime
updated_at: datetime
```

### 4.4 `customers/{customer_id}`

Shape in seed `customers.json` is internally consistent and used by `get_customer_profile`. No reshape needed. Note: does not yet include an explicit `escalation_contacts` list — escalation is captured at the company level (§5) for Tier 1. Revisit at Tier 2 if per-customer escalation becomes needed.

### 4.5 `routes/{route_id}`

Maps to `RouteDefinition` + `RouteLeg` (`models/route.py`). Current shape in seed `routes.json` has **no `company_id`**, treated as tenant-shared reference data (§3.1 option 1). Keep the shape:

```python
route_id: str
corridor_name: str
legs: list[RouteLeg]
total_distance_km: float
# no company_id, no created_at — reference data, rarely mutated
```

### 4.6 `hubs/{hub_id}`

Maps to `HubStatus` + `HubCapacityWindow`. Same treatment as routes — tenant-shared, no `company_id`. Current shape keeps.

### 4.7 `exceptions/{event_id}`

**Today: intake shape only.** The seeded docs (`EXC-2026-0001` through `EXC-2026-0005` in `seed_classifier_demo.py`) only carry `ExceptionEvent` fields (event_id, timestamp, source_channel, sender, raw_content, translations, metadata). That's the *input* to triage.

**Target Tier 1:** keep the intake shape on *create* — but after triage completes, enrich the same doc with embedded `classification`, `impact`, `triage_result` (per `Supply-Chain-Firestore-Schema-Tier1.md` §256). **Decision:** split into two collections instead of enriching one:

- **`exceptions/{event_id}`** stays the pure intake audit (immutable once created — matches current rule `allow write: if false`).
- **`triage_results/{result_id}`** is the pipeline-run audit, one doc per run, embeds classification + impact + metadata.

Rationale:
- Immutability of `exceptions` keeps the raw-intake audit clean for compliance/replay.
- Multiple runs per exception become trivially supported (re-triage after human override).
- The dashboard's "history" tab queries `triage_results` directly with cursor pagination — no need to filter embedded-subfield results.

### 4.8 NEW — `triage_results/{result_id}`

```python
result_id: str                     # UUIDv7
event_id: str                      # FK → exceptions/{event_id}
company_id: str                    # tenant anchor
user_id: str                       # Firebase uid of invoker, or "system" for scheduled
created_at: datetime               # tz-aware; the sort key for history
processing_time_ms: int            # ge=0
status: TriageStatus               # "complete" | "partial" | "escalated_to_human" | "escalated_to_human_safety"
classification: ClassificationResult | None  # embedded (flat enough — no Gemini schema issue since we're writing not reading)
impact: ImpactResult | None                   # None when Rule F (LOW severity skip) applied
summary: str
errors: list[str]
escalation_priority: EscalationPriority | None
coordinator_trace: list[dict]       # pipeline step log
tools_used: list[str]               # flattened from classification + impact for dashboard filter
# Tier 2+ human-feedback overlay
human_feedback: {
    reviewed_by: str | None,
    reviewed_at: datetime | None,
    override_severity: Severity | None,
    override_priority: list[str] | None,
    override_reasoning: str | None
} | None
```

### 4.9 NEW — `audit_events/{event_id}`

Mirror of `audit_event()` helper events that matter for the dashboard. Written by the `AuditLogMiddleware` or tool layer, Admin SDK only.

```python
event_id: str                       # UUIDv7
event: str                          # canonical event name, §6 in observability.md
correlation_id: str                 # request UUID, joins to related logs
user_id: str                        # Firebase uid or "system"
company_id: str                     # tenant anchor
timestamp: datetime                 # tz-aware
# optional (per-event-type)
agent_name: str | None
tool_name: str | None
exception_id: str | None
result_id: str | None               # FK → triage_results
latency_ms: int | None
status: str | None
category: str | None                # classification result type, redacted of PII
severity: Severity | None
confidence: float | None
http_status: int | None
failure_reason: str | None          # one-line error class, NEVER free-text
source_ip: str | None               # only when abuse tracking matters
```

**Loggable keys only.** No raw prompts, no free-text user input, no emails/phones. PII-drop processor in `utils/logging.py` is the backstop.

### 4.10 `festival_calendar/{festival_id}` + `monsoon_regions/{region_id}`

Per authoritative spec. Tenant-shared, auth-read, admin-write. Full seed content in §10.

---

## 5. Company Profile Expansion Spec

Goal (c) — escalation matrix, business hours, holiday calendar, preferred language, communication style, SLA templates by customer tier. Proposed JSON schema:

```jsonc
{
  "company_id": "comp_nimblefreight",
  "name": "NimbleFreight Logistics Pvt. Ltd.",
  "profile_summary": "...",
  "num_trucks": 45,
  "num_employees": 120,
  "regions_of_operation": ["delhi_ncr", "rajasthan", "gujarat", "tamil_nadu", "karnataka"],
  "carriers": ["Delhivery", "Rivigo", "Blue Dart", "IntrCity SmartBus Cargo", "VRL Logistics"],
  "customer_portfolio": {
    "d2c_percentage": 0.25,
    "b2b_percentage": 0.35,
    "b2b_enterprise_percentage": 0.40,
    "top_customers": ["MediQuick Pharma", "FreshKart Groceries", "StyleVerse Fashion"]
  },
  "avg_daily_revenue_inr": 3500000,
  "active": true,

  "preferred_language": "english",
  "communication_style": {
    "tone": "concise",
    "formality": "formal",
    "default_channels": ["email", "whatsapp"],
    "emoji_policy": "none",
    "language_policy": "english_primary_hinglish_customer_facing"
  },

  "business_hours": {
    "timezone": "Asia/Kolkata",
    "weekday_start": "08:00",
    "weekday_end": "20:00",
    "saturday_start": "08:00",
    "saturday_end": "14:00",
    "sunday_open": false,
    "after_hours_contact_role": "on_call_dispatcher"
  },

  "holiday_calendar": [
    {"date": "2026-04-14", "name": "Ambedkar Jayanti", "observance": "closed"},
    {"date": "2026-08-15", "name": "Independence Day", "observance": "closed"},
    {"date": "2026-10-02", "name": "Gandhi Jayanti", "observance": "closed"},
    {"date": "2026-10-20", "name": "Diwali (Laxmi Puja)", "observance": "closed"},
    {"date": "2026-10-21", "name": "Govardhan Puja", "observance": "reduced_ops"},
    {"date": "2026-11-07", "name": "Bhai Dooj", "observance": "reduced_ops"},
    {"date": "2026-12-25", "name": "Christmas", "observance": "closed"}
  ],

  "escalation_matrix": [
    {
      "severity": "CRITICAL",
      "contacts": [
        {"name": "Rajiv Menon", "role": "COO", "phone": "+91-98101-00001", "email": "coo@nimblefreight.in", "preferred_channel": "phone", "sla_response_minutes": 15},
        {"name": "Priya Sharma", "role": "Head of Ops", "phone": "+91-98101-00002", "email": "priya.sharma@nimblefreight.in", "preferred_channel": "whatsapp", "sla_response_minutes": 15}
      ]
    },
    {
      "severity": "HIGH",
      "contacts": [
        {"name": "Priya Sharma", "role": "Head of Ops", "phone": "+91-98101-00002", "email": "priya.sharma@nimblefreight.in", "preferred_channel": "whatsapp", "sla_response_minutes": 30},
        {"name": "Amit Desai", "role": "Regional Manager (North)", "phone": "+91-98101-00003", "email": "amit.desai@nimblefreight.in", "preferred_channel": "email", "sla_response_minutes": 60}
      ]
    },
    {
      "severity": "MEDIUM",
      "contacts": [
        {"name": "Dispatch Desk", "role": "dispatch_team", "phone": "+91-98101-00099", "email": "dispatch@nimblefreight.in", "preferred_channel": "email", "sla_response_minutes": 120}
      ]
    },
    {
      "severity": "LOW",
      "contacts": [
        {"name": "Shift Supervisor", "role": "shift_supervisor", "phone": null, "email": "shift-sup@nimblefreight.in", "preferred_channel": "email", "sla_response_minutes": 240}
      ]
    }
  ],

  "sla_templates": [
    {"customer_tier": "b2b_enterprise", "on_time_threshold_hours": 24, "penalty_per_hour_delayed_inr": 10000, "max_penalty_inr": 500000, "breach_triggers_refund": false, "breach_triggers_service_credit": true},
    {"customer_tier": "high_value",     "on_time_threshold_hours": 36, "penalty_per_hour_delayed_inr": 4000,  "max_penalty_inr": 200000, "breach_triggers_refund": true,  "breach_triggers_service_credit": false},
    {"customer_tier": "repeat_standard","on_time_threshold_hours": 48, "penalty_per_hour_delayed_inr": 1500,  "max_penalty_inr": 50000,  "breach_triggers_refund": false, "breach_triggers_service_credit": false},
    {"customer_tier": "new",            "on_time_threshold_hours": 72, "penalty_per_hour_delayed_inr": 500,   "max_penalty_inr": 15000,  "breach_triggers_refund": false, "breach_triggers_service_credit": true}
  ],

  "created_at": "2019-01-15T08:00:00+05:30",
  "updated_at": "2026-04-18T09:00:00+05:30"
}
```

### Pydantic sub-models (extension of `CompanyProfile`)

```python
class EscalationContact(BaseModel):
    name: str
    role: str
    phone: str | None
    email: str
    preferred_channel: Literal["phone", "whatsapp", "email", "sms"]
    sla_response_minutes: int = Field(..., ge=1)

class EscalationEntry(BaseModel):
    severity: Severity
    contacts: list[EscalationContact]

class CommunicationStyle(BaseModel):
    tone: Literal["concise", "detailed", "bullet_points"]
    formality: Literal["formal", "casual"]
    default_channels: list[Literal["phone", "whatsapp", "email", "sms"]]
    emoji_policy: Literal["none", "sparingly", "liberal"] = "none"
    language_policy: str  # free-form descriptor

class BusinessHours(BaseModel):
    timezone: str                    # IANA
    weekday_start: str               # HH:MM
    weekday_end: str
    saturday_start: str | None
    saturday_end: str | None
    sunday_open: bool = False
    after_hours_contact_role: str | None

class Holiday(BaseModel):
    date: date                       # Python date, not datetime
    name: str
    observance: Literal["closed", "reduced_ops", "observed"]

class SLATemplate(BaseModel):
    customer_tier: Literal["b2b_enterprise", "high_value", "repeat_standard", "new"]
    on_time_threshold_hours: int
    penalty_per_hour_delayed_inr: int
    max_penalty_inr: int
    breach_triggers_refund: bool
    breach_triggers_service_credit: bool
```

**Integration note.** The `CompanyProfile.to_markdown()` method already renders a `## Business Context` section for the Coordinator's `<company_context>` block. Extend it to append an `## Escalation Matrix` section when severity ≥ HIGH is classified — agents that draft communications (Tier 2 Resolution, Tier 3 Comms) consume it. Do not render the full holiday calendar into every prompt — pass only the next 30 days' entries.

---

## 6. Users Profile Spec

Aligns with existing `UserContext`. Doc ID must equal Firebase Auth `uid`. **Two users per tenant in seed** — one Head-of-Ops (coordinator persona) and one Dispatcher (operator persona).

```jsonc
{
  "user_id": "firebase_uid_of_priya",
  "company_id": "comp_nimblefreight",
  "name": "Priya Sharma",
  "email": "priya.sharma@nimblefreight.in",
  "role": "Head of Operations",
  "experience_years": 8,
  "city": "Delhi",
  "state": "Delhi",
  "timezone": "Asia/Kolkata",
  "avg_daily_shipments": 45,
  "avg_daily_exceptions": 8,
  "busiest_days": ["Monday", "Thursday", "Friday"],
  "workload_classification": "overloaded",
  "preferred_language": "english",
  "tone": "concise",
  "formality": "formal",
  "notification_channels": ["email", "whatsapp"],
  "working_hours": {"start": "08:00", "end": "20:00"},
  "override_patterns": [],
  "learned_priorities": {},
  "created_at": "2022-03-15T09:00:00+05:30",
  "last_active": "2026-04-18T08:30:00+05:30"
}
```

### Role enum — recommend

`"Head of Operations" | "Exception Coordinator" | "Dispatcher" | "Regional Manager" | "Shift Supervisor"`. Kept as free-form string today (matches `UserContext.role: str`) to avoid a premature enum; promote once the admin UI lands.

### Tie to Firebase Auth custom claims

| Claim | Source | Scope |
|---|---|---|
| `uid` | Firebase Auth | identifies user |
| `company_id` | set via `scripts/set_custom_claims.py` (Admin SDK) | identifies tenant; rule gate |
| `role` (optional, Tier 2) | same script | coarse-grained role for rule branching |

Custom claims are capped at 1KB (Firebase limit). Keep claims to identifiers — the Firestore `users/{uid}` doc carries everything else.

### Claim refresh discipline

Per `zettel-firestore-multi-tenant.md`: after `set_custom_user_claims()`, clients must force `getIdToken(true)` or wait up to 1 hour for auto-refresh. Document in the onboarding flow.

---

## 7. Complete Firestore Rules Rewrite

Replaces `infra/firestore.rules` in full. Adds `routes`, `hubs`, `triage_results`, `audit_events`. Keeps existing anchors.

```javascript
rules_version = '2';

// Multi-tenant Firestore rules for Supply Chain Exception Triage.
// Authoritative source: docs/research/firestore-utilization-audit-tier1.md §7.
// Companion: docs/research/zettel-firestore-multi-tenant.md.
//
// Invariant: every tenant document carries a top-level `company_id` field
// AND every authenticated user's ID token carries `company_id` as a custom
// claim (set via scripts/set_custom_claims.py). Rules compare the two.
//
// Tenant-shared reference collections (festival_calendar, monsoon_regions,
// routes, hubs) are authenticated-read + admin-write. They carry no
// company_id because the underlying network/calendar data is not tenant-
// specific in Tier 1.
//
// Admin SDK bypasses these rules entirely (server-side has full access).
// Every Admin SDK write site is audited in docs/sessions/2026-04-XX-
// firestore-build.md when the build lands.

service cloud.firestore {
  match /databases/{database}/documents {

    // --- Helpers ---

    function isAuthed() {
      return request.auth != null;
    }

    function hasCompanyClaim() {
      return isAuthed() && request.auth.token.company_id is string
        && request.auth.token.company_id.size() > 0;
    }

    function isCompanyMember(cid) {
      return hasCompanyClaim() && request.auth.token.company_id == cid;
    }

    function incomingIsOwnCompany() {
      return hasCompanyClaim()
        && request.auth.token.company_id == request.resource.data.company_id;
    }

    // --- Tenant-shared reference (authenticated read only) ---

    match /festival_calendar/{festivalId} {
      allow read: if isAuthed();
      allow write: if false;  // Admin SDK only
    }

    match /monsoon_regions/{regionId} {
      allow read: if isAuthed();
      allow write: if false;  // Admin SDK only
    }

    match /routes/{routeId} {
      allow read: if isAuthed();
      allow write: if false;  // Admin SDK only — logistics network is read-only at runtime
    }

    match /hubs/{hubId} {
      allow read: if isAuthed();
      allow write: if false;
    }

    // --- Tenant data ---

    match /companies/{companyId} {
      allow read: if isCompanyMember(companyId);
      allow write: if false;  // Admin SDK only — onboarding flow
    }

    match /users/{userId} {
      // Users read their own profile. Onboarding + claim updates go
      // through the Admin SDK (scripts/set_custom_claims.py + a future
      // Cloud Function on signup).
      allow read: if isAuthed() && request.auth.uid == userId;
      allow write: if false;
    }

    match /shipments/{shipmentId} {
      allow read: if isCompanyMember(resource.data.company_id);
      allow create: if incomingIsOwnCompany();
      allow update, delete: if isCompanyMember(resource.data.company_id)
                             && incomingIsOwnCompany();
    }

    match /customers/{customerId} {
      allow read: if isCompanyMember(resource.data.company_id);
      allow create: if incomingIsOwnCompany();
      allow update, delete: if isCompanyMember(resource.data.company_id)
                             && incomingIsOwnCompany();
    }

    match /exceptions/{exceptionId} {
      // Intake audit. Immutable — members read; server writes only.
      allow read: if isCompanyMember(resource.data.company_id);
      allow write: if false;
    }

    match /triage_results/{resultId} {
      // Pipeline-run audit. Members read their tenant's results; server writes only.
      allow read: if isCompanyMember(resource.data.company_id);
      allow write: if false;
    }

    match /audit_events/{eventId} {
      // High-signal audit events mirrored from structured logs for the
      // dashboard history view. Members read; server writes only.
      allow read: if isCompanyMember(resource.data.company_id);
      allow write: if false;
    }

    // Explicit deny-all catch-all for any unlisted collection.
    match /{path=**} {
      allow read, write: if false;
    }
  }
}
```

### Rule-by-rule mental test

| Operation | Expected | Rule firing |
|---|---|---|
| Authed user from `comp_X` reads `shipments/{shp}` where doc has `company_id=comp_X` | Allow | `isCompanyMember(resource.data.company_id)` matches |
| Authed user from `comp_X` reads `shipments/{shp}` where doc has `company_id=comp_Y` | Deny | claim ≠ resource.data.company_id |
| Authed user from `comp_X` creates `shipments/{new}` with `company_id=comp_Y` in body | Deny | `incomingIsOwnCompany()` false on create |
| Authed user reads `routes/ROUTE-MUM-PUNE-01` | Allow | `isAuthed()` only — reference data |
| Anonymous (no token) reads any collection | Deny | `isAuthed()` false |
| Any client writes `exceptions/*` | Deny | `allow write: if false` — Admin SDK only |
| Any client writes `triage_results/*` | Deny | same |
| User reads `users/{own_uid}` | Allow | `request.auth.uid == userId` |
| User reads `users/{other_uid}` | Deny | uid mismatch |
| Any client reads unknown collection `foo/bar` | Deny | catch-all |
| Admin SDK does anything | Allow (rules bypassed) | documented at Admin SDK call sites |

### Custom-claim-missing edge case

`hasCompanyClaim()` checks both presence and string-type to guard against a misconfigured token (e.g. claim set to `null` or missing entirely). Without the guard, `request.auth.token.company_id == cid` returns false-ish on `null` but could produce surprising behavior on adversarial input. Defense-in-depth.

---

## 8. Complete Indexes Plan

Replaces `infra/firestore.indexes.json`. 12 composite indexes total. Each annotated with the query that uses it.

```json
{
  "indexes": [
    {
      "collectionGroup": "shipments",
      "queryScope": "COLLECTION",
      "fields": [
        {"fieldPath": "company_id", "order": "ASCENDING"},
        {"fieldPath": "status", "order": "ASCENDING"},
        {"fieldPath": "vehicle_id", "order": "ASCENDING"}
      ],
      "__comment": "Impact.get_affected_shipments(scope_type='vehicle_id'). Tool filters on status first then vehicle_id; leading 'company_id' is enforced when the tool gains tenant scoping. Current code omits company_id filter and relies on Admin SDK bypass — see §12."
    },
    {
      "collectionGroup": "shipments",
      "queryScope": "COLLECTION",
      "fields": [
        {"fieldPath": "company_id", "order": "ASCENDING"},
        {"fieldPath": "status", "order": "ASCENDING"},
        {"fieldPath": "route_id", "order": "ASCENDING"}
      ],
      "__comment": "Impact.get_affected_shipments(scope_type='route_id')."
    },
    {
      "collectionGroup": "shipments",
      "queryScope": "COLLECTION",
      "fields": [
        {"fieldPath": "company_id", "order": "ASCENDING"},
        {"fieldPath": "status", "order": "ASCENDING"},
        {"fieldPath": "region", "order": "ASCENDING"}
      ],
      "__comment": "Impact.get_affected_shipments(scope_type='region')."
    },
    {
      "collectionGroup": "shipments",
      "queryScope": "COLLECTION",
      "fields": [
        {"fieldPath": "company_id", "order": "ASCENDING"},
        {"fieldPath": "customer_id", "order": "ASCENDING"},
        {"fieldPath": "status", "order": "ASCENDING"}
      ],
      "__comment": "Reserved for dashboard 'per-customer active shipments'. No runtime user today — revisit after Tier 1."
    },
    {
      "collectionGroup": "shipments",
      "queryScope": "COLLECTION",
      "fields": [
        {"fieldPath": "company_id", "order": "ASCENDING"},
        {"fieldPath": "status", "order": "ASCENDING"},
        {"fieldPath": "deadline", "order": "ASCENDING"}
      ],
      "__comment": "Reserved for dashboard 'urgent shipments by deadline'. No runtime user today."
    },
    {
      "collectionGroup": "exceptions",
      "queryScope": "COLLECTION",
      "fields": [
        {"fieldPath": "company_id", "order": "ASCENDING"},
        {"fieldPath": "created_at", "order": "DESCENDING"}
      ],
      "__comment": "Dashboard history pagination — chronological tenant feed."
    },
    {
      "collectionGroup": "exceptions",
      "queryScope": "COLLECTION",
      "fields": [
        {"fieldPath": "company_id", "order": "ASCENDING"},
        {"fieldPath": "sender.user_id", "order": "ASCENDING"},
        {"fieldPath": "created_at", "order": "DESCENDING"}
      ],
      "__comment": "Per-user history. Note: path `sender.user_id` nested field — only valid if sender docs consistently include user_id; today sender is {name, role}. Flag to reshape exceptions.sender or defer this index."
    },
    {
      "collectionGroup": "triage_results",
      "queryScope": "COLLECTION",
      "fields": [
        {"fieldPath": "company_id", "order": "ASCENDING"},
        {"fieldPath": "created_at", "order": "DESCENDING"}
      ],
      "__comment": "Dashboard 'recent triage runs' — primary history-tab query."
    },
    {
      "collectionGroup": "triage_results",
      "queryScope": "COLLECTION",
      "fields": [
        {"fieldPath": "company_id", "order": "ASCENDING"},
        {"fieldPath": "status", "order": "ASCENDING"},
        {"fieldPath": "created_at", "order": "DESCENDING"}
      ],
      "__comment": "Dashboard filter 'only escalated' or 'only complete'."
    },
    {
      "collectionGroup": "triage_results",
      "queryScope": "COLLECTION",
      "fields": [
        {"fieldPath": "company_id", "order": "ASCENDING"},
        {"fieldPath": "classification.exception_type", "order": "ASCENDING"},
        {"fieldPath": "created_at", "order": "DESCENDING"}
      ],
      "__comment": "Dashboard analytics tile 'by exception type'."
    },
    {
      "collectionGroup": "audit_events",
      "queryScope": "COLLECTION",
      "fields": [
        {"fieldPath": "company_id", "order": "ASCENDING"},
        {"fieldPath": "timestamp", "order": "DESCENDING"}
      ],
      "__comment": "Dashboard audit feed — chronological."
    },
    {
      "collectionGroup": "audit_events",
      "queryScope": "COLLECTION",
      "fields": [
        {"fieldPath": "company_id", "order": "ASCENDING"},
        {"fieldPath": "event", "order": "ASCENDING"},
        {"fieldPath": "timestamp", "order": "DESCENDING"}
      ],
      "__comment": "Filter by event type (agent_invoked, escalation_triggered, permission_denied)."
    }
  ],
  "fieldOverrides": []
}
```

### Index diffs vs. current

| Old (drop) | Reason |
|---|---|
| `exceptions (company_id, classification.exception_type)` | Promoted to `triage_results` — that's where classification lives post-refactor |
| `exceptions (company_id, classification.severity)` | Same |
| `exceptions (company_id, user_id, created_at DESC)` | `user_id` isn't a top-level field on current intake shape — reshaped to `sender.user_id` in new index; defer until `sender` shape is normalized |

| New (add) | Query |
|---|---|
| `shipments` reordered from `(company_id, vehicle_id, status)` to `(company_id, status, vehicle_id)` | `.where(status==).where(vehicle_id==)` order in `impact.tools.get_affected_shipments` — Firestore requires the equality fields in a specific index order; reorder matches tool query order. **Strategic recommendation per Firebase best practices: put more-selective equality first.** `status='in_transit'` filters out delivered noise (selectivity ≈ 80%); vehicle_id is a sharper filter (selectivity ≈ 99%). Argument could be made either way — keep `(status, vehicle_id)` for monotonic write alignment. Both orderings work for a pure `==, ==` composite. |
| Similar reorder for route_id + region indexes | Same logic |
| `triage_results (company_id, created_at DESC)` | Dashboard primary |
| `triage_results (company_id, status, created_at DESC)` | Dashboard status filter |
| `triage_results (company_id, classification.exception_type, created_at DESC)` | Analytics tile |
| `audit_events (company_id, timestamp DESC)` | Audit feed |
| `audit_events (company_id, event, timestamp DESC)` | Audit filter by event type |

### Index build time

Firestore composite index builds take 30s–several minutes on an empty collection and scale with document count. On prod, run `firebase deploy --only firestore:indexes` well before the demo — builds are visible in the Firebase console and block queries until complete. Emulator indexes are instant (no-op).

---

## 9. Seed Data Strategy

### 9.1 Consolidated entrypoint — `scripts/seed_all.py`

Single CLI replacing the four existing scripts.

```
usage: seed_all.py [-h] [--target {emulator,dev,prod,demo}] [--wipe]
                   [--collections COLLECTIONS]

Options:
  --target {emulator,dev,prod,demo}
        Default: emulator. "demo" is an alias for emulator + a curated
        NH-48 scenario subset. "dev" and "prod" hit real Firestore via
        get_firestore_client().

  --wipe
        Delete every document in selected collections before seeding.
        Refuses to run on target=prod. Requires --confirm-wipe flag
        for target=dev (extra guard).

  --collections COLLECTIONS
        Comma-separated list. Defaults to all. e.g.
        --collections companies,users,shipments

  --dry-run
        Print what would be written; no Firestore calls.
```

Core loop (pseudocode):

```python
COLLECTIONS = {
    "companies":         ("companies.json",        "company_id"),
    "users":             ("users.json",            "user_id"),
    "customers":         ("customers.json",        "customer_id"),
    "routes":            ("routes.json",           "route_id"),
    "hubs":              ("hubs.json",             "hub_id"),
    "shipments":         ("shipments.json",        "shipment_id"),
    "exceptions":        ("exceptions.json",       "event_id"),
    "festival_calendar": ("festival_calendar.json","festival_id"),
    "monsoon_regions":   ("monsoon_regions.json",  "region_id"),
}

async def seed(db, wipe: bool, collections: list[str]) -> None:
    for name in collections:
        filename, id_field = COLLECTIONS[name]
        docs = json.loads((SEED_DIR / filename).read_text())
        if wipe:
            await _wipe(db, name)       # batched delete, 500 per batch
        for doc in docs:
            await db.collection(name).document(doc[id_field]).set(doc)  # idempotent
```

### 9.2 Idempotency discipline

- Use `.set()` not `.add()` — doc IDs come from the JSON, re-running overwrites with the same content.
- On `--wipe`, delete via `query.stream()` + `batch.delete()` (Firestore batch max 500 operations).
- Never mutate `created_at` on re-seed — preserve original via `merge=True` or explicit `created_at` in seed JSON.

### 9.3 `scripts/seed/` file-by-file plan

| File | Current | Target | Doc count |
|---|---|---|---|
| `companies.json` | `[]` | **Rewrite** — SwiftLogix + NimbleFreight (the two tenants we demo), both with the §5 expansion shape | 2 |
| `users.json` | `[]` | **Rewrite** — 2 users per tenant (Head of Ops + Dispatcher) | 4 |
| `customers.json` | 7 docs | Keep | 7 |
| `routes.json` | 4 docs | Keep | 4 |
| `hubs.json` | 12 docs | Keep | 12 |
| `shipments.json` | 25 docs | Keep | 25 |
| `exceptions.json` | missing | **Create** — pull the 5 docs from `seed_classifier_demo.py` + NH-48 flagship into JSON | ~7 |
| `festival_calendar.json` | `[]` | **Rewrite** — 10-15 Indian festivals spanning next 12 months | 12 |
| `monsoon_regions.json` | `[]` | **Rewrite** — 6-8 Indian monsoon zones | 7 |
| `companies_nimblefreight.json` | 1 doc | **Delete** — folded into consolidated `companies.json` | 0 |

### 9.4 Migration — what to do with the four old scripts

Option A: delete immediately after `seed_all.py` passes verification.
Option B: keep as thin wrappers that `print("DEPRECATED: use seed_all.py --collections X")` and exit non-zero.

Recommend **Option B for one sprint** — catches any hidden caller in CI / Makefile / session notes — then delete.

### 9.5 NH-48 flagship determinism

The demo storyline hinges on:
- Exception `EXC-2026-NH48-001` — truck breakdown on NH-48 at a specific milestone
- Vehicle `MH-04-XX-1234` carries 4 shipments (`SHP-2024-4821` to `SHP-2024-4824`)
- Each of the 4 shipments has a different customer (BlushBox / FitHaus / KraftHeaven / CoreCloud) — one per customer tier
- Noise shipments (`SHP-2024-4831`, `-4832`, `-4833`) on different vehicles — Impact must NOT match them

Seed `shipments.json` already satisfies this exactly. Add two flagship exceptions to `exceptions.json`:

- `EXC-2026-NH48-001` — vehicle breakdown, Hinglish/English mix, for Classifier Hinglish path
- `EXC-2026-NH48-002` — safety-override variant (hazmat spill) — tests SafetyEscalation flow
- `EXC-2026-NH48-003` — FSSAI regulatory backup — tests regulatory exception type

---

## 10. Seed JSON Content for the 4 Stub Files

### 10.1 `companies.json` (full content, 2 docs)

```json
[
  {
    "company_id": "swiftlogix-001",
    "name": "SwiftLogix Pvt. Ltd.",
    "profile_summary": "Small 3PL operator based in Mumbai, serving the Mumbai-Gujarat-Chennai corridor. Specializes in FMCG, cosmetics launches, and pharmaceutical distribution with a D2C-heavy customer portfolio.",
    "num_trucks": 15,
    "num_employees": 42,
    "regions_of_operation": ["maharashtra", "gujarat", "karnataka", "tamil_nadu"],
    "carriers": ["BlueDart", "Delhivery", "DTDC", "Gati"],
    "customer_portfolio": {
      "d2c_percentage": 0.55,
      "b2b_percentage": 0.25,
      "b2b_enterprise_percentage": 0.20,
      "top_customers": ["cust_blushbox", "cust_corecloud", "cust_fithaus"]
    },
    "avg_daily_revenue_inr": 800000,
    "active": true,

    "preferred_language": "hinglish",
    "communication_style": {
      "tone": "concise",
      "formality": "casual",
      "default_channels": ["whatsapp", "phone"],
      "emoji_policy": "sparingly",
      "language_policy": "hinglish_internal_english_customer_facing"
    },

    "business_hours": {
      "timezone": "Asia/Kolkata",
      "weekday_start": "08:00",
      "weekday_end": "21:00",
      "saturday_start": "08:00",
      "saturday_end": "18:00",
      "sunday_open": false,
      "after_hours_contact_role": "on_call_dispatcher"
    },

    "holiday_calendar": [
      {"date": "2026-04-14", "name": "Ambedkar Jayanti", "observance": "closed"},
      {"date": "2026-05-01", "name": "Maharashtra Day", "observance": "closed"},
      {"date": "2026-08-15", "name": "Independence Day", "observance": "closed"},
      {"date": "2026-09-17", "name": "Ganesh Chaturthi", "observance": "reduced_ops"},
      {"date": "2026-10-02", "name": "Gandhi Jayanti", "observance": "closed"},
      {"date": "2026-10-20", "name": "Diwali (Laxmi Puja)", "observance": "closed"},
      {"date": "2026-10-21", "name": "Govardhan Puja", "observance": "reduced_ops"},
      {"date": "2026-12-25", "name": "Christmas", "observance": "closed"}
    ],

    "escalation_matrix": [
      {
        "severity": "CRITICAL",
        "contacts": [
          {"name": "Ravi Shetty",    "role": "Founder/CEO",   "phone": "+91-98200-10001", "email": "ravi@swiftlogix.in",    "preferred_channel": "phone",    "sla_response_minutes": 10},
          {"name": "Anjali Kulkarni","role": "Head of Ops",   "phone": "+91-98200-10002", "email": "anjali@swiftlogix.in",  "preferred_channel": "whatsapp", "sla_response_minutes": 15}
        ]
      },
      {
        "severity": "HIGH",
        "contacts": [
          {"name": "Anjali Kulkarni","role": "Head of Ops",   "phone": "+91-98200-10002", "email": "anjali@swiftlogix.in",  "preferred_channel": "whatsapp", "sla_response_minutes": 30},
          {"name": "Suresh Pillai",  "role": "Fleet Manager", "phone": "+91-98200-10003", "email": "suresh@swiftlogix.in",  "preferred_channel": "phone",    "sla_response_minutes": 45}
        ]
      },
      {
        "severity": "MEDIUM",
        "contacts": [
          {"name": "Dispatch Desk",  "role": "dispatch_team", "phone": "+91-98200-10099", "email": "dispatch@swiftlogix.in","preferred_channel": "whatsapp", "sla_response_minutes": 90}
        ]
      },
      {
        "severity": "LOW",
        "contacts": [
          {"name": "Shift Supervisor", "role": "shift_supervisor", "phone": null, "email": "shift-sup@swiftlogix.in", "preferred_channel": "email", "sla_response_minutes": 240}
        ]
      }
    ],

    "sla_templates": [
      {"customer_tier": "b2b_enterprise","on_time_threshold_hours": 24, "penalty_per_hour_delayed_inr": 8000, "max_penalty_inr": 400000,"breach_triggers_refund": false, "breach_triggers_service_credit": true},
      {"customer_tier": "high_value",    "on_time_threshold_hours": 24, "penalty_per_hour_delayed_inr": 5000, "max_penalty_inr": 150000,"breach_triggers_refund": true,  "breach_triggers_service_credit": false},
      {"customer_tier": "repeat_standard","on_time_threshold_hours": 48,"penalty_per_hour_delayed_inr": 1000, "max_penalty_inr": 30000, "breach_triggers_refund": false, "breach_triggers_service_credit": false},
      {"customer_tier": "new",           "on_time_threshold_hours": 72, "penalty_per_hour_delayed_inr": 500,  "max_penalty_inr": 15000, "breach_triggers_refund": false, "breach_triggers_service_credit": true}
    ],

    "created_at": "2020-09-01T09:00:00+05:30",
    "updated_at": "2026-04-18T09:00:00+05:30"
  },

  {
    "company_id": "comp_nimblefreight",
    "name": "NimbleFreight Logistics Pvt. Ltd.",
    "profile_summary": "Mid-size 3PL operator headquartered in Delhi NCR, covering the Delhi-Rajasthan-Gujarat corridor and South India (Tamil Nadu, Karnataka). Specializes in cold chain pharma distribution, perishable grocery logistics, and fashion retail last-mile.",
    "num_trucks": 45,
    "num_employees": 120,
    "regions_of_operation": ["delhi_ncr", "rajasthan", "gujarat", "tamil_nadu", "karnataka"],
    "carriers": ["Delhivery", "Rivigo", "Blue Dart", "IntrCity SmartBus Cargo", "VRL Logistics"],
    "customer_portfolio": {
      "d2c_percentage": 0.25,
      "b2b_percentage": 0.35,
      "b2b_enterprise_percentage": 0.40,
      "top_customers": ["cust_mediquick", "cust_freshkart", "cust_styleverse"]
    },
    "avg_daily_revenue_inr": 3500000,
    "active": true,

    "preferred_language": "english",
    "communication_style": {
      "tone": "concise",
      "formality": "formal",
      "default_channels": ["email", "whatsapp"],
      "emoji_policy": "none",
      "language_policy": "english_primary_hinglish_customer_facing"
    },

    "business_hours": {
      "timezone": "Asia/Kolkata",
      "weekday_start": "07:00",
      "weekday_end": "22:00",
      "saturday_start": "07:00",
      "saturday_end": "16:00",
      "sunday_open": false,
      "after_hours_contact_role": "regional_shift_lead"
    },

    "holiday_calendar": [
      {"date": "2026-04-14", "name": "Ambedkar Jayanti", "observance": "closed"},
      {"date": "2026-08-15", "name": "Independence Day", "observance": "closed"},
      {"date": "2026-10-02", "name": "Gandhi Jayanti", "observance": "closed"},
      {"date": "2026-10-20", "name": "Diwali (Laxmi Puja)", "observance": "closed"},
      {"date": "2026-10-21", "name": "Govardhan Puja", "observance": "reduced_ops"},
      {"date": "2026-11-07", "name": "Bhai Dooj", "observance": "reduced_ops"},
      {"date": "2026-12-25", "name": "Christmas", "observance": "closed"}
    ],

    "escalation_matrix": [
      {
        "severity": "CRITICAL",
        "contacts": [
          {"name": "Rajiv Menon",  "role": "COO",           "phone": "+91-98101-00001","email": "coo@nimblefreight.in",         "preferred_channel": "phone",    "sla_response_minutes": 15},
          {"name": "Priya Sharma", "role": "Head of Ops",   "phone": "+91-98101-00002","email": "priya.sharma@nimblefreight.in","preferred_channel": "whatsapp", "sla_response_minutes": 15}
        ]
      },
      {
        "severity": "HIGH",
        "contacts": [
          {"name": "Priya Sharma", "role": "Head of Ops",            "phone": "+91-98101-00002","email": "priya.sharma@nimblefreight.in","preferred_channel": "whatsapp","sla_response_minutes": 30},
          {"name": "Amit Desai",   "role": "Regional Manager (North)","phone":"+91-98101-00003","email": "amit.desai@nimblefreight.in",  "preferred_channel": "email",   "sla_response_minutes": 60}
        ]
      },
      {
        "severity": "MEDIUM",
        "contacts": [
          {"name": "Dispatch Desk", "role": "dispatch_team", "phone": "+91-98101-00099","email": "dispatch@nimblefreight.in","preferred_channel": "email", "sla_response_minutes": 120}
        ]
      },
      {
        "severity": "LOW",
        "contacts": [
          {"name": "Shift Supervisor", "role": "shift_supervisor", "phone": null, "email": "shift-sup@nimblefreight.in", "preferred_channel": "email", "sla_response_minutes": 240}
        ]
      }
    ],

    "sla_templates": [
      {"customer_tier": "b2b_enterprise","on_time_threshold_hours": 24, "penalty_per_hour_delayed_inr": 15000,"max_penalty_inr": 750000,"breach_triggers_refund": false,"breach_triggers_service_credit": true},
      {"customer_tier": "high_value",    "on_time_threshold_hours": 36, "penalty_per_hour_delayed_inr": 4000, "max_penalty_inr": 200000,"breach_triggers_refund": true, "breach_triggers_service_credit": false},
      {"customer_tier": "repeat_standard","on_time_threshold_hours": 12,"penalty_per_hour_delayed_inr": 3000, "max_penalty_inr": 80000, "breach_triggers_refund": true, "breach_triggers_service_credit": false},
      {"customer_tier": "new",           "on_time_threshold_hours": 72, "penalty_per_hour_delayed_inr": 500,  "max_penalty_inr": 15000, "breach_triggers_refund": false,"breach_triggers_service_credit": true}
    ],

    "created_at": "2019-01-15T08:00:00+05:30",
    "updated_at": "2026-04-18T09:00:00+05:30"
  }
]
```

### 10.2 `users.json` (full content, 4 docs)

**Note on `user_id`.** The seed IDs below are placeholder UIDs. Before `seed_all.py --live`, either (a) create matching Firebase Auth users in the emulator/prod and substitute real UIDs, or (b) pre-create Auth users via a helper and backfill the JSON. The `scripts/set_custom_claims.py` workflow needs to run against these same UIDs to attach `company_id` claims.

```json
[
  {
    "user_id": "u_swiftlogix_headops_anjali",
    "company_id": "swiftlogix-001",
    "name": "Anjali Kulkarni",
    "email": "anjali@swiftlogix.in",
    "role": "Head of Operations",
    "experience_years": 12,
    "city": "Mumbai",
    "state": "Maharashtra",
    "timezone": "Asia/Kolkata",
    "avg_daily_shipments": 18,
    "avg_daily_exceptions": 4,
    "busiest_days": ["Monday", "Friday"],
    "workload_classification": "manageable",
    "preferred_language": "hinglish",
    "tone": "concise",
    "formality": "casual",
    "notification_channels": ["whatsapp", "phone"],
    "working_hours": {"start": "08:00", "end": "20:00"},
    "override_patterns": [],
    "learned_priorities": {},
    "created_at": "2020-09-01T09:00:00+05:30",
    "last_active": "2026-04-18T08:00:00+05:30"
  },
  {
    "user_id": "u_swiftlogix_dispatcher_ramesh",
    "company_id": "swiftlogix-001",
    "name": "Ramesh Kumar",
    "email": "ramesh.dispatch@swiftlogix.in",
    "role": "Dispatcher",
    "experience_years": 4,
    "city": "Mumbai",
    "state": "Maharashtra",
    "timezone": "Asia/Kolkata",
    "avg_daily_shipments": 22,
    "avg_daily_exceptions": 6,
    "busiest_days": ["Monday", "Thursday", "Friday", "Saturday"],
    "workload_classification": "overloaded",
    "preferred_language": "hinglish",
    "tone": "bullet_points",
    "formality": "casual",
    "notification_channels": ["whatsapp"],
    "working_hours": {"start": "07:00", "end": "19:00"},
    "override_patterns": [],
    "learned_priorities": {},
    "created_at": "2022-06-20T09:00:00+05:30",
    "last_active": "2026-04-18T07:45:00+05:30"
  },
  {
    "user_id": "u_nimble_headops_priya",
    "company_id": "comp_nimblefreight",
    "name": "Priya Sharma",
    "email": "priya.sharma@nimblefreight.in",
    "role": "Head of Operations",
    "experience_years": 8,
    "city": "Delhi",
    "state": "Delhi",
    "timezone": "Asia/Kolkata",
    "avg_daily_shipments": 45,
    "avg_daily_exceptions": 8,
    "busiest_days": ["Monday", "Thursday", "Friday"],
    "workload_classification": "overloaded",
    "preferred_language": "english",
    "tone": "concise",
    "formality": "formal",
    "notification_channels": ["email", "whatsapp"],
    "working_hours": {"start": "08:00", "end": "20:00"},
    "override_patterns": [],
    "learned_priorities": {},
    "created_at": "2022-03-15T09:00:00+05:30",
    "last_active": "2026-04-18T08:30:00+05:30"
  },
  {
    "user_id": "u_nimble_dispatcher_deepika",
    "company_id": "comp_nimblefreight",
    "name": "Deepika Rao",
    "email": "deepika.rao@nimblefreight.in",
    "role": "Dispatcher",
    "experience_years": 3,
    "city": "Delhi",
    "state": "Delhi",
    "timezone": "Asia/Kolkata",
    "avg_daily_shipments": 38,
    "avg_daily_exceptions": 9,
    "busiest_days": ["Monday", "Tuesday", "Thursday", "Friday"],
    "workload_classification": "overloaded",
    "preferred_language": "english",
    "tone": "bullet_points",
    "formality": "casual",
    "notification_channels": ["whatsapp", "email"],
    "working_hours": {"start": "07:00", "end": "19:00"},
    "override_patterns": [],
    "learned_priorities": {},
    "created_at": "2023-01-10T09:00:00+05:30",
    "last_active": "2026-04-18T07:30:00+05:30"
  }
]
```

### 10.3 `festival_calendar.json` (12 docs)

Covers 12 months from demo date (2026-04-18). Rule D (Classifier festival context) is deferred but data lands now.

```json
[
  {"festival_id": "akshaya_tritiya_2026", "name": "Akshaya Tritiya", "date": "2026-05-10", "duration_days": 1, "significance": "commerce_auspicious", "affected_regions": ["all_india"], "commerce_impact": "moderate_increase", "typical_shipment_deadline_sensitivity": "high"},
  {"festival_id": "eid_ul_fitr_2026", "name": "Eid ul-Fitr", "date": "2026-05-17", "duration_days": 2, "significance": "religious", "affected_regions": ["all_india"], "commerce_impact": "moderate_increase", "typical_shipment_deadline_sensitivity": "high"},
  {"festival_id": "raksha_bandhan_2026", "name": "Raksha Bandhan", "date": "2026-08-28", "duration_days": 1, "significance": "cultural", "affected_regions": ["all_india"], "commerce_impact": "massive_surge", "typical_shipment_deadline_sensitivity": "critical"},
  {"festival_id": "ganesh_chaturthi_2026", "name": "Ganesh Chaturthi", "date": "2026-09-17", "duration_days": 10, "significance": "religious_regional", "affected_regions": ["maharashtra", "karnataka", "goa"], "commerce_impact": "massive_surge", "typical_shipment_deadline_sensitivity": "critical"},
  {"festival_id": "durga_puja_2026", "name": "Durga Puja", "date": "2026-10-17", "duration_days": 5, "significance": "religious_regional", "affected_regions": ["west_bengal", "odisha", "assam", "bihar"], "commerce_impact": "massive_surge", "typical_shipment_deadline_sensitivity": "critical"},
  {"festival_id": "dussehra_2026", "name": "Dussehra", "date": "2026-10-22", "duration_days": 1, "significance": "religious", "affected_regions": ["all_india"], "commerce_impact": "moderate_increase", "typical_shipment_deadline_sensitivity": "high"},
  {"festival_id": "karwa_chauth_2026", "name": "Karwa Chauth", "date": "2026-11-01", "duration_days": 1, "significance": "cultural", "affected_regions": ["north_india"], "commerce_impact": "moderate_increase", "typical_shipment_deadline_sensitivity": "high"},
  {"festival_id": "diwali_2026", "name": "Diwali (Laxmi Puja)", "date": "2026-10-20", "duration_days": 5, "significance": "religious_major", "affected_regions": ["all_india"], "commerce_impact": "massive_surge", "typical_shipment_deadline_sensitivity": "critical"},
  {"festival_id": "bhai_dooj_2026", "name": "Bhai Dooj", "date": "2026-11-07", "duration_days": 1, "significance": "cultural", "affected_regions": ["all_india"], "commerce_impact": "moderate_increase", "typical_shipment_deadline_sensitivity": "normal"},
  {"festival_id": "christmas_2026", "name": "Christmas", "date": "2026-12-25", "duration_days": 1, "significance": "religious", "affected_regions": ["all_india"], "commerce_impact": "moderate_increase", "typical_shipment_deadline_sensitivity": "high"},
  {"festival_id": "new_year_2027", "name": "New Year", "date": "2027-01-01", "duration_days": 1, "significance": "cultural", "affected_regions": ["all_india"], "commerce_impact": "minimal", "typical_shipment_deadline_sensitivity": "normal"},
  {"festival_id": "holi_2027", "name": "Holi", "date": "2027-03-13", "duration_days": 2, "significance": "cultural_religious", "affected_regions": ["all_india_ex_south"], "commerce_impact": "moderate_increase", "typical_shipment_deadline_sensitivity": "normal"}
]
```

### 10.4 `monsoon_regions.json` (7 docs)

```json
[
  {
    "region_id": "maharashtra",
    "display_name": "Maharashtra (Western Ghats + Konkan)",
    "coverage_states": ["Maharashtra", "Goa"],
    "monsoon_season": {"start_month": 6, "end_month": 9, "peak_months": [7, 8]},
    "current_status": "inactive",
    "current_intensity": "none",
    "known_risks": ["flooding_on_mumbai_pune_expressway", "landslides_lonavala_ghats"],
    "last_updated": "2026-04-18T09:00:00+05:30"
  },
  {
    "region_id": "kerala",
    "display_name": "Kerala (Southwest Monsoon arrival)",
    "coverage_states": ["Kerala", "Karnataka (coastal)"],
    "monsoon_season": {"start_month": 6, "end_month": 9, "peak_months": [6, 7]},
    "current_status": "ending_soon",
    "current_intensity": "none",
    "known_risks": ["urban_flooding_kochi", "landslides_idukki"],
    "last_updated": "2026-04-18T09:00:00+05:30"
  },
  {
    "region_id": "west_bengal",
    "display_name": "West Bengal (Eastern Monsoon)",
    "coverage_states": ["West Bengal", "Odisha", "Assam"],
    "monsoon_season": {"start_month": 6, "end_month": 10, "peak_months": [7, 8, 9]},
    "current_status": "inactive",
    "current_intensity": "none",
    "known_risks": ["cyclone_landfall_bay_of_bengal", "flooding_kolkata"],
    "last_updated": "2026-04-18T09:00:00+05:30"
  },
  {
    "region_id": "rajasthan",
    "display_name": "Rajasthan (Northwestern monsoon edge)",
    "coverage_states": ["Rajasthan"],
    "monsoon_season": {"start_month": 7, "end_month": 9, "peak_months": [8]},
    "current_status": "inactive",
    "current_intensity": "none",
    "known_risks": ["flash_flooding_eastern_rajasthan"],
    "last_updated": "2026-04-18T09:00:00+05:30"
  },
  {
    "region_id": "tamil_nadu",
    "display_name": "Tamil Nadu (Northeast monsoon)",
    "coverage_states": ["Tamil Nadu", "Puducherry"],
    "monsoon_season": {"start_month": 10, "end_month": 12, "peak_months": [11]},
    "current_status": "inactive",
    "current_intensity": "none",
    "known_risks": ["cyclone_landfall_chennai", "urban_flooding_chennai"],
    "last_updated": "2026-04-18T09:00:00+05:30"
  },
  {
    "region_id": "delhi_ncr",
    "display_name": "Delhi NCR (North Indian plains)",
    "coverage_states": ["Delhi", "Haryana", "Uttar Pradesh (west)"],
    "monsoon_season": {"start_month": 7, "end_month": 9, "peak_months": [7, 8]},
    "current_status": "inactive",
    "current_intensity": "none",
    "known_risks": ["yamuna_flooding", "waterlogging_major_roads"],
    "last_updated": "2026-04-18T09:00:00+05:30"
  },
  {
    "region_id": "gujarat",
    "display_name": "Gujarat (Western India)",
    "coverage_states": ["Gujarat"],
    "monsoon_season": {"start_month": 6, "end_month": 9, "peak_months": [7, 8]},
    "current_status": "inactive",
    "current_intensity": "none",
    "known_risks": ["flooding_ahmedabad_vadodara", "port_disruption_kandla"],
    "last_updated": "2026-04-18T09:00:00+05:30"
  }
]
```

---

## 11. Seed Data for Flagship Scenarios

### 11.1 `exceptions.json` — proposed content (7 docs)

Pulls the 5 existing inlined exceptions from `seed_classifier_demo.py` plus 2 NH-48 flagship additions.

```json
[
  {
    "event_id": "EXC-2026-0001",
    "company_id": "swiftlogix-001",
    "timestamp": "2026-04-16T06:30:00+00:00",
    "source_channel": "manual_entry",
    "sender": {"name": "Dispatch Control", "role": "operations", "user_id": "u_swiftlogix_dispatcher_ramesh"},
    "raw_content": "BlueDart truck BD-MH12-4521 broke down on the Mumbai-Pune Expressway near Lonavala at 06:30 IST. Driver reports engine failure. 12 packages onboard for delivery today including 3 high-value B2B shipments for MegaMart. Mechanic ETA 3 hours. No injuries reported.",
    "original_language": null,
    "english_translation": null,
    "media_urls": [],
    "metadata": {"company_id": "swiftlogix-001"}
  },
  {
    "event_id": "EXC-2026-0002",
    "company_id": "swiftlogix-001",
    "timestamp": "2026-04-16T08:00:00+00:00",
    "source_channel": "manual_entry",
    "sender": {"name": "Port Liaison", "role": "operations", "user_id": "u_swiftlogix_dispatcher_ramesh"},
    "raw_content": "URGENT: Heavy monsoon flooding in Nhava Sheva port area since last night. Multiple container yards waterlogged. Access roads to JNPT blocked. Port operations suspended until further notice. Estimated 200+ containers affected across all operators. Water level still rising. Met department predicts continued heavy rain for 48 hours.",
    "original_language": null,
    "english_translation": null,
    "media_urls": [],
    "metadata": {"company_id": "swiftlogix-001"}
  },
  {
    "event_id": "EXC-2026-0003",
    "company_id": "swiftlogix-001",
    "timestamp": "2026-04-16T10:15:00+00:00",
    "source_channel": "customer_escalation",
    "sender": {"name": "Rajesh Kumar", "role": "VP Operations, MegaMart India", "user_id": null},
    "raw_content": "FINAL WARNING - This is our third escalation this month regarding delivery delays. Order #MM-2026-8834 was promised delivery by April 14th for our Diwali campaign pre-stock. It's April 16th and we still don't have the shipment. Our contract specifies Rs 50,000/day penalty for delays beyond 48 hours. We are seriously reconsidering our logistics partnership. Please resolve immediately or we will initiate contract termination proceedings.",
    "original_language": null,
    "english_translation": null,
    "media_urls": [],
    "metadata": {"company_id": "swiftlogix-001"}
  },
  {
    "event_id": "EXC-2026-0004",
    "company_id": "swiftlogix-001",
    "timestamp": "2026-04-16T14:20:00+00:00",
    "source_channel": "manual_entry",
    "sender": {"name": "Highway Patrol Desk", "role": "emergency", "user_id": null},
    "raw_content": "EMERGENCY: Chemical tanker overturned on NH8 near Vapi, Gujarat at 14:20 IST. Driver injured and admitted to local hospital. Chemical spill reported on highway - substance identified as industrial solvent. NHAI has closed a 2km stretch. Our 3 trucks are stuck behind the blockade with perishable cargo. Police and fire services on scene. PESO has been notified. Estimated road clearance: 6-8 hours minimum.",
    "original_language": null,
    "english_translation": null,
    "media_urls": [],
    "metadata": {"company_id": "swiftlogix-001"}
  },
  {
    "event_id": "EXC-2026-0005",
    "company_id": "swiftlogix-001",
    "timestamp": "2026-04-16T11:45:00+00:00",
    "source_channel": "carrier_portal_alert",
    "sender": {"name": "Customs Broker", "role": "compliance", "user_id": null},
    "raw_content": "Customs hold at Chennai port for shipment CHN-2026-442. Missing phytosanitary certificate for agricultural goods consignment. FSSAI inspection has been triggered. Expected clearance delay 2-3 business days. No perishables in this particular shipment. Documentation team working on obtaining the certificate from the exporter.",
    "original_language": null,
    "english_translation": null,
    "media_urls": [],
    "metadata": {"company_id": "swiftlogix-001"}
  },
  {
    "event_id": "EXC-2026-NH48-001",
    "company_id": "swiftlogix-001",
    "timestamp": "2026-04-16T05:45:00+00:00",
    "source_channel": "whatsapp_text",
    "sender": {"name": "Ramesh Kumar", "role": "Dispatcher", "user_id": "u_swiftlogix_dispatcher_ramesh"},
    "raw_content": "Bhai truck MH-04-XX-1234 NH-48 pe 90km milestone pe breakdown ho gaya. Engine coolant leak. 4 shipments onboard: BlushBox, FitHaus, KraftHeaven aur CoreCloud. BlushBox ka Influencer launch kal subah 10 baje hai - critical! Mechanic 2 ghante me aayega. Backup vehicle arrange karo urgently.",
    "original_language": "hinglish",
    "english_translation": "Brother, truck MH-04-XX-1234 has broken down on NH-48 at the 90 km milestone. Engine coolant leak. 4 shipments onboard: BlushBox, FitHaus, KraftHeaven, and CoreCloud. The BlushBox influencer launch is tomorrow morning at 10 AM — critical! Mechanic will arrive in 2 hours. Arrange a backup vehicle urgently.",
    "media_urls": [],
    "metadata": {"company_id": "swiftlogix-001", "vehicle_id": "MH-04-XX-1234", "route_id": "ROUTE-MUM-PUNE-01"}
  },
  {
    "event_id": "EXC-2026-NH48-002",
    "company_id": "swiftlogix-001",
    "timestamp": "2026-04-16T06:00:00+00:00",
    "source_channel": "phone_call_transcript",
    "sender": {"name": "Highway Patrol (Lonavala)", "role": "emergency", "user_id": null},
    "raw_content": "Caller reports: 'Hazmat leak from stationary SwiftLogix vehicle MH-04-XX-1234 on NH-48 shoulder near Lonavala. Looks like brake fluid + engine coolant mix. Small spill contained by sand. Driver safe. We need you to dispatch a hazmat-certified cleanup team and file PESO incident report within 2 hours per Maharashtra state regulations. Highway lane 1 restricted for the next 45 minutes.'",
    "original_language": null,
    "english_translation": null,
    "media_urls": [],
    "metadata": {"company_id": "swiftlogix-001", "vehicle_id": "MH-04-XX-1234", "safety_incident": true}
  }
]
```

### 11.2 Reference-consistency checklist (NH-48 scenario)

| Reference | Exists in seed? | File |
|---|---|---|
| `MH-04-XX-1234` in shipments | Yes — 4 shipments (`SHP-2024-4821` to `-4824`) | `shipments.json` |
| `ROUTE-MUM-PUNE-01` | Yes | `routes.json` |
| `hub_mumbai`, `hub_pune`, `hub_lonavala_transit` (route's hubs) | Yes | `hubs.json` |
| `cust_blushbox`, `cust_fithaus`, `cust_kraftheaven`, `cust_corecloud` | Yes | `customers.json` |
| `swiftlogix-001` company | Yes (after §10.1 rewrite) | `companies.json` |
| `u_swiftlogix_dispatcher_ramesh` (sender) | Yes (after §10.2 rewrite) | `users.json` |
| Noise shipments not on MH-04-XX-1234 | Yes — SHP-2024-4831 (MH-12-ZZ-9900), -4832 (MH-09-AA-3300), -4833 (MH-14-BB-7700) | `shipments.json` |
| Delivered shipments (negative tests for `status=='in_transit'` filter) | Yes — 4801, 4802, 4900, 4980, 4981, 4982 | `shipments.json` |

Every flagship reference resolves. No dangling IDs.

---

## 12. Firestore Client Wiring

### 12.1 Location + shape

`src/supply_chain_triage/core/config.py:get_firestore_client` — already built, correct.

Key properties:
- **Memoized** via `functools.lru_cache(maxsize=1)` — one `AsyncClient` per process.
- **Emulator auto-detect** — Settings' `firestore_emulator_host` is exported to `FIRESTORE_EMULATOR_HOST` before `AsyncClient(...)` construction (CR9 fix, in code).
- **Lazy import** — `from google.cloud import firestore` happens inside the function so unit tests that don't need Firestore don't pay the import cost.
- **Vendor-import discipline** — `config.py` is the ONLY file in `core/` allowed to import `google.cloud.firestore`. Ruff `TID251` waiver is explicit in `pyproject.toml` `[tool.ruff.lint.per-file-ignores]`.

### 12.2 AsyncClient concurrency

Per [Firebase best practices — networking](https://firebase.google.com/docs/functions/networking), creating a global/singleton client provides connection pooling and is the recommended pattern for serverless environments. `google.cloud.firestore.AsyncClient` uses gRPC transport with its own pooled channels; a single `AsyncClient` instance safely handles many concurrent coroutines. No per-request client creation, ever.

### 12.3 Emulator wiring

Two entry points:
1. **`.env` file or env var** — `FIRESTORE_EMULATOR_HOST=localhost:8080`. Pydantic-settings reads it, `get_firestore_client()` honors it.
2. **Direct env mutation** (scripts/tests) — e.g. `scripts/seed_emulator.py` does `os.environ["FIRESTORE_EMULATOR_HOST"] = "localhost:8080"` BEFORE importing Firestore. Critical: the env var must be set before the SDK import chain runs, because the SDK captures the env at import time in some versions.

### 12.4 `GCP_PROJECT_ID` for emulator

Firestore emulator accepts any project ID — `"demo-no-project"` is the conventional "don't talk to prod" marker. Our Settings requires `GCP_PROJECT_ID` as a non-empty string; seed scripts default it to `"supply-chain-triage-dev"`.

### 12.5 Testing patterns

Three tiers per `.claude/rules/testing.md`:

| Tier | Client | Fixture |
|---|---|---|
| Unit | `mockfirestore` (in-memory fake) | `tests/fixtures/fake_firestore.py` |
| Integration | Real emulator (`firebase emulators:start --only firestore`) | `tests/conftest.py` checks `FIRESTORE_EMULATOR_HOST` |
| E2E (Tier 3+) | Real emulator + Auth emulator + full ADK + FastAPI stack | TBD |

`tests/conftest.py` pattern (existing) — clears collections between tests to prevent bleed. Reference: `tests/unit/core/` directory already created per current git status.

### 12.6 Admin SDK vs. AsyncClient

Per `.claude/rules/imports.md`:

| Context | Use |
|---|---|
| Scripts (seed, set-custom-claims) | `firebase_admin` for Auth operations; `google.cloud.firestore.AsyncClient` for Firestore |
| Middleware (token verify) | `firebase_admin.auth` |
| Tools (Firestore queries) | `google.cloud.firestore.AsyncClient` via `get_firestore_client()` |
| Memory adapters | `google.cloud.firestore.AsyncClient` |
| Agent code | NEVER any vendor SDK — must go through tools |

Reason: `firebase_admin.firestore.client()` returns a **sync** client. Agents are async — never mix.

### 12.7 Known friction — Impact tool missing `company_id` filter

Current `impact.get_affected_shipments` queries:

```python
query = (
    db.collection(_SHIPMENTS_COLLECTION)
    .where(filter=FieldFilter("status", "==", "in_transit"))
    .where(filter=FieldFilter(scope_type, "==", scope_value))
)
```

No `company_id` filter. This works because:
- Admin SDK (server-side via `get_firestore_client()`) bypasses rules.
- Seed data happens to separate tenants by seed composition.

But: in prod with multiple tenants and a real multi-tenant deployment, this query would leak cross-tenant shipments. **Must add `.where(FieldFilter("company_id", "==", ...))`** once the tool plumbs `company_id` from agent state. Tracked as follow-up in §16.

---

## 13. Migration / Deploy Plan

### 13.1 Emulator path (dev loop, CI, demo)

```bash
# 1. Start emulators
firebase emulators:start --only firestore,auth

# 2. Seed (idempotent)
uv run python scripts/seed_all.py --target=emulator

# 3. Set custom claims for test users
FIREBASE_AUTH_EMULATOR_HOST=localhost:9099 \
  uv run python scripts/set_custom_claims.py \
  --uid u_swiftlogix_headops_anjali --company-id swiftlogix-001

# 4. Agent playground
adk web src/supply_chain_triage/modules/triage/agents
```

### 13.2 Prod path (staging / prod)

```bash
# 1. Deploy rules (seconds)
firebase deploy --only firestore:rules --project sct-staging

# 2. Deploy indexes (minutes — watch the console)
firebase deploy --only firestore:indexes --project sct-staging

# 3. Wait for index builds to reach "Enabled" state
firebase firestore:indexes --project sct-staging  # verify

# 4. Seed reference data + demo tenants (one-time)
GCP_PROJECT_ID=sct-staging uv run python scripts/seed_all.py --target=prod \
  --collections=festival_calendar,monsoon_regions,routes,hubs

# 5. For demo-day prod: seed the two tenants + their users + demo scenario
uv run python scripts/seed_all.py --target=prod --collections=companies,users,customers,shipments,exceptions
```

### 13.3 Rule change safety

- Test with `firebase emulators:exec` + rules tests before deploy.
- Staging first, prod second, never direct to prod.
- Keep previous rule version in git — rollback is `git revert` + `firebase deploy --only firestore:rules`.

### 13.4 Index build caveats

- Composite index builds on populated collections take minutes to hours. An empty collection indexes in seconds.
- Queries requiring a not-yet-built index fail with `FAILED_PRECONDITION`. Never deploy indexes at the same moment you deploy code that needs them — deploy indexes **first**, wait, then code.
- See [Firestore index management](https://firebase.google.com/docs/firestore/query-data/indexing).

---

## 14. Cost Model

Firestore free tier per day (per [Firestore pricing](https://firebase.google.com/docs/firestore/quotas)):

| Op | Free daily |
|---|---|
| Document reads | 50,000 |
| Document writes | 20,000 |
| Document deletes | 20,000 |
| Stored data | 1 GiB |
| Network egress | 10 GiB/month |

### 14.1 Per-triage-run cost

| Op | Count | Where |
|---|---|---|
| Read `exceptions/{id}` | 1 | Classifier fetcher + Impact fetcher (cached per turn so ~1 actual) |
| Read `companies/{id}` | 1 | Classifier |
| Read `users/{id}` | 1 | Coordinator context (Tier 2+) |
| Query `shipments` by scope | 1 (returns N docs, billed as reads) | Impact |
| Read affected `customers/{id}` | N (one per affected shipment) | Impact, but cached |
| Read `routes/{id}` | 1 | Impact |
| Read `hubs/{id}` | ~4-5 (legs × 2 unique hubs) | Impact |
| Write `triage_results/{new_id}` | 1 | Coordinator after-agent |
| Write `audit_events/{new_id}` × ~3 | 3 | `audit_event()` high-signal subset |
| **Total per run** | **~12 reads + 4 writes** | |

### 14.2 Judge demo window (100 runs)

- Reads: 100 × ~12 = **~1,200** (≪ 50,000 free daily)
- Writes: 100 × 4 = **~400** (≪ 20,000 free daily)
- Stored data: <1 MB (tiny)

**Conclusion:** demo traffic fits inside free tier by two orders of magnitude. No cost risk for Tier 1.

### 14.3 Scaling checkpoint (Tier 2+)

If Sprint 2's Resolution agent adds 2 more writes per run (generator output + judge result) and we hit 10k runs/day, we're at 60k writes/day. Would need to budget or consolidate writes. Revisit at Tier 2 boundary.

---

## 15. Testing Patterns

### 15.1 Unit tests (no Firestore)

Use `mockfirestore` or a hand-rolled fake. Place fakes in `tests/fixtures/`.

```python
# tests/fixtures/fake_firestore.py (proposed)
from mockfirestore import MockFirestore, AsyncMockFirestore

@pytest.fixture
def fake_firestore(monkeypatch):
    """Replace get_firestore_client with an in-memory fake."""
    client = AsyncMockFirestore()
    monkeypatch.setattr(
        "supply_chain_triage.core.config.get_firestore_client",
        lambda: client,
    )
    return client
```

Reference: `.claude/rules/testing.md` §6.

### 15.2 Integration tests (emulator)

Markered via `@pytest.mark.integration`, skipped unless `FIRESTORE_EMULATOR_HOST` is set.

```python
# tests/conftest.py pattern
@pytest.fixture
async def firestore_client():
    """Real emulator client — resets collections between tests."""
    os.environ["FIRESTORE_EMULATOR_HOST"] = "localhost:8080"
    from supply_chain_triage.core.config import get_firestore_client
    client = get_firestore_client()
    yield client
    # Teardown: delete all seeded docs
    for coll in ["exceptions", "triage_results", "audit_events"]:
        async for doc in client.collection(coll).stream():
            await doc.reference.delete()
```

### 15.3 Rules tests (Tier 2 commitment)

`firebase emulators:exec "npm run test:rules"` with `@firebase/rules-unit-testing`. Defer to Tier 2 but document now: each rule matcher deserves 2 tests (positive case, negative case) at minimum.

### 15.4 Seed idempotency test

```python
@pytest.mark.integration
async def test_seed_all_is_idempotent(firestore_client):
    await run_seed_all()
    docs_first = [d async for d in firestore_client.collection("shipments").stream()]
    await run_seed_all()  # re-run
    docs_second = [d async for d in firestore_client.collection("shipments").stream()]
    assert len(docs_first) == len(docs_second) == 25
```

---

## 16. Concrete Next-Session Task List

Ordered. File-by-file. Time estimates assume familiarity with the codebase.

### Phase A — Rules + indexes (15 min)

1. **Edit** `infra/firestore.rules` — replace with §7 content. Adds `routes`, `hubs`, `triage_results`, `audit_events` matchers; adds `hasCompanyClaim()` guard. [5 min]
2. **Edit** `infra/firestore.indexes.json` — replace with §8 content. 12 indexes. Remove the 2 obsolete `exceptions.classification.*` indexes (promoted to `triage_results`). [5 min]
3. **Smoke-test**: start emulator, manually verify rule edge cases with a tiny Python script using the Auth emulator token + two tenants. [5 min]

### Phase B — Seed consolidation (45 min)

4. **Create** `scripts/seed/exceptions.json` — §11.1 content (7 docs). [5 min]
5. **Rewrite** `scripts/seed/companies.json` — §10.1 content (2 docs). [5 min]
6. **Rewrite** `scripts/seed/users.json` — §10.2 content (4 docs). [5 min]
7. **Rewrite** `scripts/seed/festival_calendar.json` — §10.3 content (12 docs). [3 min]
8. **Rewrite** `scripts/seed/monsoon_regions.json` — §10.4 content (7 docs). [3 min]
9. **Delete** `scripts/seed/companies_nimblefreight.json` (merged into `companies.json`). [1 min]
10. **Create** `scripts/seed_all.py` per §9.1. Copy idempotent loop from `seed_impact_demo.py`, add `--wipe` + `--collections` flags. [20 min]
11. **Create** deprecation shims for the 4 old scripts (print-and-exit-nonzero wrappers). [3 min]

### Phase C — New collections wiring (60 min)

12. **Add** `modules/triage/memory/triage_archive.py` — thin `write_triage_result(result: TriageResult, user_id: str) -> None` helper using Admin SDK. [20 min]
13. **Hook into Coordinator** `after_agent_callback` — call `write_triage_result` at the end of a successful pipeline run. State plumbs `user_id` + `company_id` from auth middleware. [15 min]
14. **Create** `middleware/audit_log.py` `audit_event()` helper per `.claude/rules/observability.md` §6, with Firestore mirror write for high-signal events (`agent_invoked`, `classification_result`, `escalation_triggered`, `permission_denied`). [20 min]
15. **Add** ruff/import-linter exceptions if any (should be none — all imports land in allowed layers). [5 min]

### Phase D — Tests (30 min)

16. **Create** `tests/fixtures/fake_firestore.py` — `mockfirestore` fixture. [10 min]
17. **Create** `tests/integration/memory/test_triage_archive.py` — emulator round-trip. [15 min]
18. **Create** `tests/integration/scripts/test_seed_all.py` — idempotency + wipe. [5 min]

### Phase E — Fix Impact tool tenant leak (15 min)

19. **Edit** `impact/tools.py:get_affected_shipments` — add `.where(FieldFilter("company_id", "==", company_id))` sourced from `tool_context.state["triage:company_id"]`. Add failing-without-company_id guard. [10 min]
20. **Update** corresponding tests. [5 min]

### Phase F — Docs + session note (15 min)

21. **Write** `docs/sessions/2026-04-XX-firestore-build.md` — what shipped, what's deferred, Admin SDK audit site list. [15 min]

### Total: ~3 hours

---

## 17. Open Questions for User

Decisions deferred from this audit — needed before or during the build session:

1. **Exception retention policy.** User said "full historical exception archive with retention" — what retention period? 90 days (ops-friendly default), 1 year (compliance-friendly), indefinite (audit-friendly, costs scale)? And same question for `triage_results` + `audit_events`. Affects: Firestore TTL policies (collection-level, set at field in doc), cost ceiling, dashboard history depth.

2. **Tenant-prefixed doc IDs.** User mentioned this as a goal. Two interpretations: (a) prefix ID with `company_id` (e.g. `swiftlogix-001__SHP-2024-4821`) for double-defense even if rule fails, or (b) use subcollections under `companies/{cid}/shipments/{shipmentId}`. Current audit assumes neither — flat top-level collections with `company_id` field. Which direction? (Note: subcollections break cross-tenant collection-group queries if we ever need them — doesn't apply to Tier 1 but locks us in.)

3. **Firestore region.** `asia-south1` (Mumbai, lowest latency for Indian users) or `nam5` / `us-central1` (cheaper free tier, closer to Gemini endpoints)? Indian demo traffic argues for Mumbai; Gemini API latency is a wash since it's a different service. Recommend `asia-south1` for prod; dev can be anywhere.

4. **`routes` + `hubs` — tenant-scoped in Tier 2?** Today treated as tenant-shared reference data. If competitive IP concerns matter, migrate to tenant-scoped with `company_id` field + index + rule change. Flag for Tier 2 scope call.

5. **Real user UIDs vs placeholder UIDs in `users.json`.** Seed plan uses placeholder IDs (`u_swiftlogix_headops_anjali`). Before going to prod (or even Auth-emulator-backed demo), must either (a) create matching Firebase Auth users programmatically in seed, or (b) accept manual Auth user creation + UID backfill. Recommend (a) — extend `seed_all.py` to also create Auth users when `--target in (emulator, dev)`.

6. **`audit_events` cost ceiling.** §14 cost model assumes ~3 writes per triage run. If the full `audit_event()` canonical-names table in `.claude/rules/observability.md` fans out to Firestore (8+ events per run), we hit 800 writes per 100 demo runs — still under budget but tighter. Confirm which events mirror to Firestore vs. stay log-only.

7. **Sender shape on `exceptions`.** Current `sender` is `{name, role}` plus optional `user_id`. The index `(company_id, sender.user_id, created_at DESC)` requires consistent presence of `sender.user_id`. Either make `user_id` required (migrate old docs, add default) or drop this index until we normalize. Recommend: require `user_id` on new writes, backfill seeds (done in §11.1 already for applicable cases), drop the index for now.

8. **Admin SDK allow-list.** Rules say "Admin SDK bypasses rules." Current Admin SDK call sites: every tool, every seed script, the proposed `audit_event` Firestore writer. Should we enumerate them in a `docs/sessions/*-security.md` audit doc as a standing practice? Recommend yes, before first prod deploy.

---

## Sources

- [[Supply-Chain-Firestore-Schema-Tier1]] — authoritative schema spec (repo-local)
- [[zettel-firestore-multi-tenant]] — custom claims + rules reasoning (repo-local)
- [Structure security rules for Cloud Firestore](https://firebase.google.com/docs/firestore/security/rules-structure)
- [Best practices for Cloud Firestore](https://firebase.google.com/docs/firestore/best-practices)
- [Firebase custom claims — Admin SDK](https://firebase.google.com/docs/auth/admin/custom-claims)
- [Firestore rules and auth](https://firebase.google.com/docs/rules/rules-and-auth)
- [Manage indexes in Cloud Firestore](https://firebase.google.com/docs/firestore/query-data/indexing)
- [Index types in Cloud Firestore](https://firebase.google.com/docs/firestore/query-data/index-overview)
- [Class AsyncClient — Python client reference](https://cloud.google.com/python/docs/reference/firestore/latest/google.cloud.firestore_v1.async_client.AsyncClient)
- [Optimizing networking — Cloud Functions for Firebase](https://firebase.google.com/docs/functions/networking)
- [How to model Firestore multi-tenant data for speed and safety](https://wild.codes/candidate-toolkit-question/how-do-you-model-firestore-multi-tenant-data-for-speed-and-safety)
- [Firebase Firestore rules recipes — Martin Capodici](https://martincapodici.com/2022/11/29/firebase-firestore-rules-recipes-and-tips/)
- [Implementing Multi Tenancy with Firebase (KTree)](https://ktree.com/blog/implementing-multi-tenancy-with-firebase-a-step-by-step-guide.html)
- [Optimizing Firestore Queries With Composite Indexes (peerdh)](https://peerdh.com/blogs/programming-insights/optimizing-firestore-queries-with-composite-indexes)
- [How to Create and Manage Composite Indexes in Firestore (OneUptime, 2026-02)](https://oneuptime.com/blog/post/2026-02-17-how-to-create-and-manage-composite-indexes-in-firestore/view)
- `.claude/rules/firestore.md`, `.claude/rules/security.md`, `.claude/rules/observability.md`, `.claude/rules/imports.md`, `.claude/rules/models.md`, `.claude/rules/agents.md`, `.claude/rules/tools.md`, `.claude/rules/placement.md`, `.claude/rules/architecture-layers.md`, `.claude/rules/logging.md`, `.claude/rules/deployment.md`, `.claude/rules/new-feature-checklist.md`, `.claude/rules/code-quality.md` — repo-local rule files

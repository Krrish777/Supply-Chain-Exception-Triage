---
title: "Firestore Data Model (Tier 1)"
type: deep-dive
domains: [supply-chain, data-model, hackathon]
last_updated: 2026-04-10
status: active
confidence: high
sources: ["[[Supply-Chain-Agent-Spec-Coordinator]]", "[[Supply-Chain-Agent-Spec-Classifier]]", "[[Supply-Chain-Agent-Spec-Impact]]", "[[Supply-Chain-Demo-Scenario-Tier1]]"]
---

# Firestore Data Model — Tier 1

> [!abstract] Purpose
> Complete Firestore schema for Tier 1 of the Exception Triage Module. Defines collections, document structures, indexes, security rules, and seed data requirements. All schemas are derived from agent specs (Coordinator, Classifier, Impact) and anchored to the NH-48 demo scenario.

## Architecture Overview

```
Firestore (operational data)
├── companies/           ← Multi-tenant company profiles
├── users/               ← User profiles (injected into Coordinator context)
├── shipments/           ← Live operational shipments (queried by Impact Agent)
├── customers/           ← Customer profiles (queried by Impact Agent)
├── exceptions/          ← Audit trail of every exception processed
├── festival_calendar/   ← Static reference (Classifier tool)
└── monsoon_regions/     ← Static reference (Classifier tool)

Supermemory (memory/patterns, NOT in Firestore)
├── User context (personas, preferences)      ← via company_context/user_context
├── Customer exception history                 ← via lookup_customer_exception_history
└── Similar past exceptions (semantic search)  ← via lookup_similar_past_exceptions
```

**Separation principle (research-backed from [LangChain Context Engineering](https://docs.langchain.com/oss/python/langchain/context-engineering)):**
- Operational/transactional data → Firestore
- Memory/pattern/semantic data → Supermemory
- Static reference → Firestore (simpler than separate store)

---

## Collection 1: `companies`

Multi-tenant company profiles. One document per tenant.

```typescript
// companies/{company_id}
{
  company_id: string,              // Document ID (e.g., "comp_nimblefreight")
  name: string,                    // "NimbleFreight Logistics"
  profile_summary: string,         // One-paragraph company description

  // Operational metadata
  num_trucks: number,              // 18
  num_employees: number,           // 25
  regions_of_operation: string[],  // ["maharashtra_west", "gujarat_south"]
  carriers: string[],              // ["BlueDart", "Delhivery", "Ecom Express"]

  // Customer portfolio summary (for Coordinator context injection)
  customer_portfolio: {
    d2c_percentage: number,        // 0.70
    b2b_percentage: number,        // 0.20
    b2b_enterprise_percentage: number,  // 0.10
    top_customers: string[]        // ["cust_blushbox", "cust_fithaus"]
  },

  // Revenue (used by Classifier severity validator — 5% threshold)
  avg_daily_revenue_inr: number,   // 2500000 (₹25L daily)

  // Audit
  created_at: Timestamp,
  updated_at: Timestamp,
  active: boolean                  // true
}
```

**Indexes:** None needed for Tier 1 (queried by document ID only).

---

## Collection 2: `users`

User profiles for exception coordinators. Injected into Coordinator context via Supermemory hydration.

```typescript
// users/{user_id}
{
  user_id: string,                 // Document ID (e.g., "user_priya_001")
  company_id: string,              // Reference to companies/{company_id}

  // Identity
  name: string,                    // "Priya Sharma"
  email: string,
  role: string,                    // "Exception Coordinator"
  experience_years: number,        // 3

  // Location
  city: string,                    // "Mumbai"
  state: string,                   // "Maharashtra"
  timezone: string,                // "Asia/Kolkata"

  // Workload (populated over time)
  avg_daily_shipments: number,     // 20
  avg_daily_exceptions: number,    // 5
  busiest_days: string[],          // ["Monday", "Friday"]
  workload_classification: string, // "manageable" | "overloaded"

  // Communication preferences
  preferred_language: string,      // "english" | "hindi" | "hinglish"
  tone: string,                    // "concise" | "detailed" | "bullet_points"
  formality: string,               // "formal" | "casual"
  notification_channels: string[], // ["whatsapp", "email"]

  // Working hours
  working_hours: {
    start: string,                 // "09:00"
    end: string,                   // "19:00"
  },

  // Learned preferences (populated from overrides — Tier 2+)
  override_patterns: string[],     // empty in Tier 1
  learned_priorities: object,      // empty in Tier 1

  // Audit
  created_at: Timestamp,
  last_active: Timestamp
}
```

**Indexes:**
- `company_id` + `active` (if we add active filtering)

---

## Collection 3: `shipments`

Live operational shipments. Queried heavily by Impact Agent.

```typescript
// shipments/{shipment_id}
{
  shipment_id: string,             // Document ID (e.g., "SHP-2024-4821")
  company_id: string,              // Multi-tenant isolation

  // References
  customer_id: string,             // Reference to customers/{customer_id}
  vehicle_id: string,              // "MH-04-XX-1234"
  route_id: string,                // "ROUTE-MUM-PUNE-01"
  region: string,                  // "maharashtra_west"

  // Status
  status: string,                  // "in_transit" | "delivered" | "delayed" | "exception"
  created_at: Timestamp,
  updated_at: Timestamp,

  // Shipment details
  product_description: string,     // "200 units Monsoon Muse lipstick launch"
  value_inr: number,               // 850000
  weight_kg: number,               // 50
  origin: string,                  // "Mumbai warehouse"
  destination: string,             // "Pune warehouse"

  // Deadline
  deadline: Timestamp,
  deadline_type: string,           // "customer_committed" | "sla_committed" | "internal_target"

  // Rule E: Reputation risk metadata
  public_facing_deadline: boolean, // true — triggers Rule E flag
  reputation_risk_note: string,    // "Influencer campaign launches at 10 AM tomorrow"

  // SLA and penalties
  sla_terms: {
    on_time_threshold_hours: number,
    penalty_per_hour_delayed_inr: number,
    max_penalty_inr: number,
    breach_triggers_refund: boolean
  },
  penalty_amount_inr: number,      // Pre-computed max penalty exposure

  // Special notes
  special_notes: string,           // "Top priority customer, LTV ₹50L+"

  // For Impact Agent consumption
  customer_tier_snapshot: string,  // Denormalized for fast reads
  customer_type_snapshot: string,  // Denormalized: "d2c" | "b2b" | "marketplace"
}
```

**Indexes (critical for Impact Agent queries):**
- `company_id` + `vehicle_id` + `status`
- `company_id` + `route_id` + `status`
- `company_id` + `region` + `status`
- `company_id` + `customer_id` + `status`
- `company_id` + `status` + `deadline` (for "urgent shipments" queries)

---

## Collection 4: `customers`

Customer profiles. Queried by Impact Agent via `get_customer_profile`.

```typescript
// customers/{customer_id}
{
  customer_id: string,             // Document ID (e.g., "cust_blushbox")
  company_id: string,              // The 3PL that serves this customer

  // Identity
  name: string,                    // "BlushBox Beauty"
  customer_type: string,           // "d2c" | "b2b" | "marketplace"
  customer_tier: string,           // "high_value" | "repeat_standard" | "new" | "b2b_enterprise"

  // Relationship
  relationship_value_inr: number,  // 5000000 (LTV)
  churn_risk_score: number,        // 0.0 - 1.0
  active_since: Timestamp,
  total_shipments_count: number,   // 150
  successful_delivery_rate: number, // 0.96

  // SLA terms (applied to new shipments from this customer)
  default_sla_terms: {
    on_time_threshold_hours: number,
    penalty_per_hour_delayed_inr: number,
    max_penalty_inr: number
  },

  // Contact
  primary_contact: {
    name: string,
    role: string,
    phone: string,
    email: string,
    preferred_channel: string       // "whatsapp" | "email" | "phone"
  },

  // Historical reliability (from analytics)
  historical_metrics: {
    avg_resolution_satisfaction: number, // 0-1 scale
    escalation_frequency: number,
    tolerance_for_delays: string    // "low" | "medium" | "high"
  },

  // Special handling
  special_handling_notes: string,  // "CEO personally calls if delivery missed"

  created_at: Timestamp,
  updated_at: Timestamp
}
```

**Indexes:**
- `company_id` + `customer_tier`
- `company_id` + `customer_type`

---

## Collection 5: `exceptions`

Audit trail of every exception processed. Written by the triage pipeline. Becomes the source data for Supermemory "past exception history" later.

```typescript
// exceptions/{exception_id}
{
  exception_id: string,            // Document ID (UUID)
  event_id: string,                // Matches the incoming request's event_id
  company_id: string,
  user_id: string,                 // User who triggered the triage
  created_at: Timestamp,

  // Original event
  source_channel: string,          // "whatsapp_voice" | "email" | etc.
  sender: object,                  // {name, role, vehicle_id, ...}
  raw_content: string,             // Original text
  original_language: string,       // "hinglish"
  english_translation: string,     // Post-translation

  // Classification result (embedded from ClassificationResult schema)
  classification: {
    exception_type: string,
    subtype: string,
    severity: string,
    confidence: number,
    urgency_hours: number,
    key_facts: object,
    reasoning: string,
    tools_used: string[],
    safety_escalation: object | null,
    validator_escalated_from: string | null  // If validator bumped severity
  },

  // Impact result (embedded from ImpactResult schema)
  impact: {
    affected_shipments: object[],      // Array of ShipmentImpact
    total_value_at_risk_inr: number,
    total_penalty_exposure_inr: number,
    critical_path_shipment_id: string,
    recommended_priority_order: string[],
    priority_reasoning: string,
    impact_weights_used: object,
    has_reputation_risks: boolean,
    reputation_risk_shipments: string[],
    tools_used: string[]
  } | null,  // Null if Impact Agent was skipped (Rule F)

  // Final triage result
  triage_result: {
    status: string,                // "complete" | "partial" | "escalated_to_human" | "escalated_to_human_safety"
    coordinator_trace: object[],
    summary: string,
    processing_time_ms: number,
    errors: string[],
    escalation_priority: string | null
  },

  // Human feedback (Tier 2+: populated when coordinator overrides decisions)
  human_feedback: {
    reviewed_by: string | null,
    reviewed_at: Timestamp | null,
    override_severity: string | null,
    override_priority: string[] | null,
    override_reasoning: string | null
  } | null
}
```

**Indexes:**
- `company_id` + `created_at` (for chronological audit queries)
- `company_id` + `user_id` + `created_at` (for per-user history)
- `company_id` + `classification.exception_type` (for analytics)
- `company_id` + `classification.severity` (for severity analytics)

---

## Collection 6: `festival_calendar` (Static Reference)

Indian festival calendar. Static data for `get_festival_context` tool.

```typescript
// festival_calendar/{festival_id}
{
  festival_id: string,             // "diwali_2026"
  name: string,                    // "Diwali"
  date: Timestamp,                 // 2026-10-29
  duration_days: number,           // 5
  significance: string,            // "cultural_religious"
  affected_regions: string[],      // ["all_india"] or ["maharashtra", "gujarat"]
  commerce_impact: string,         // "massive_surge" | "moderate_increase" | "minimal"
  typical_shipment_deadline_sensitivity: string  // "critical" | "high" | "normal"
}
```

**Seed data for Tier 1:** Diwali, Holi, Eid (ul-Fitr, ul-Adha), Raksha Bandhan, Ganesh Chaturthi, Durga Puja, Dussehra, Karwa Chauth, Christmas, New Year. ~10-15 documents.

**Indexes:**
- `date` (for "festivals in next 30 days" queries)

---

## Collection 7: `monsoon_regions` (Static Reference)

Indian monsoon status by region. Static data for `get_monsoon_status` tool.

```typescript
// monsoon_regions/{region_id}
{
  region_id: string,               // "maharashtra_west"
  display_name: string,            // "Western Maharashtra"
  coverage_states: string[],       // ["Maharashtra", "Goa"]
  monsoon_season: {
    start_month: number,           // 6 (June)
    end_month: number,             // 9 (September)
    peak_months: number[]          // [7, 8] (July, August)
  },
  current_status: string,          // "active" | "inactive" | "ending_soon"
  current_intensity: string,       // "light" | "moderate" | "heavy" | "extreme"
  last_updated: Timestamp
}
```

**Seed data for Tier 1:** 6-8 regions covering major Indian monsoon zones (West Coast, East Coast, Northern Plains, South India, Central India, Northeast, Himalayan).

**Indexes:** None needed (queried by document ID).

---

## Security Rules (Multi-Tenant Isolation)

Critical for production: every query MUST filter by `company_id` so tenants can't see each other's data.

```javascript
// firestore.rules
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {

    // Helper: check if request is from a user belonging to the target company
    function isCompanyMember(companyId) {
      return request.auth != null
        && request.auth.token.company_id == companyId;
    }

    // Shipments: only members of the owning company can read/write
    match /shipments/{shipmentId} {
      allow read: if isCompanyMember(resource.data.company_id);
      allow write: if isCompanyMember(request.resource.data.company_id);
    }

    // Customers: same rule
    match /customers/{customerId} {
      allow read: if isCompanyMember(resource.data.company_id);
      allow write: if isCompanyMember(request.resource.data.company_id);
    }

    // Exceptions: same rule
    match /exceptions/{exceptionId} {
      allow read: if isCompanyMember(resource.data.company_id);
      allow write: if isCompanyMember(request.resource.data.company_id);
    }

    // Companies: members can read their own company; no one writes (admin only)
    match /companies/{companyId} {
      allow read: if isCompanyMember(companyId);
      allow write: if false;  // Admin SDK only
    }

    // Users: users read their own profile
    match /users/{userId} {
      allow read: if request.auth != null && request.auth.uid == userId;
      allow write: if request.auth != null && request.auth.uid == userId;
    }

    // Festival calendar + monsoon regions: public read (reference data)
    match /festival_calendar/{id} {
      allow read: if request.auth != null;
      allow write: if false;  // Admin SDK only
    }
    match /monsoon_regions/{id} {
      allow read: if request.auth != null;
      allow write: if false;  // Admin SDK only
    }
  }
}
```

---

## Seed Data Plan for Tier 1 Demo

For the Apr 24 prototype demo, we need realistic seed data aligned with the NH-48 scenario:

### 1 company
- `comp_nimblefreight` (NimbleFreight Logistics)

### 1 user
- `user_priya_001` (Priya Sharma)

### 4 customers
- `cust_blushbox` (BlushBox Beauty — high_value D2C)
- `cust_fithaus` (FitHaus Nutrition — repeat_standard D2C)
- `cust_kraftheaven` (KraftHeaven Home — new D2C)
- `cust_corecloud` (CoreCloud Tech — b2b_enterprise)

### 4 shipments (the NH-48 truck load)
- `SHP-2024-4821` (BlushBox lipstick)
- `SHP-2024-4822` (FitHaus protein boxes)
- `SHP-2024-4823` (KraftHeaven Diwali lamps)
- `SHP-2024-4824` (CoreCloud server racks)

### Additional context shipments (for Impact Agent to NOT match incorrectly)
- 5-6 other shipments on DIFFERENT vehicles, ensuring Impact Agent correctly filters by `vehicle_id == "MH-04-XX-1234"`

### Festival calendar
- 10-15 festivals spanning next 12 months

### Monsoon regions
- 6-8 Indian regions with current status

**Total: ~30-35 Firestore documents for Tier 1 demo.**

---

## Dependency: Company ID Must Flow Through Every Request

Every Firestore query, every tool call, every Supermemory lookup needs `company_id` as context. The multi-tenant isolation depends on this.

**Flow:**
1. Request arrives at FastAPI endpoint with `Authorization: Bearer <token>`
2. Middleware extracts `company_id` and `user_id` from token
3. Both are passed to ADK session state
4. Coordinator's `before_model_callback` reads from session state to fetch user/company context
5. Each agent's tools receive `company_id` as implicit parameter via session state or closure

---

## Cross-References

- [[Supply-Chain-Agent-Spec-Coordinator]] — Uses this schema for user/company context injection
- [[Supply-Chain-Agent-Spec-Classifier]] — Uses `festival_calendar` and `monsoon_regions` via tools
- [[Supply-Chain-Agent-Spec-Impact]] — Uses `shipments`, `customers` via tools
- [[Supply-Chain-Demo-Scenario-Tier1]] — The scenario that drove schema design

---
title: "Sprint 3 Test Plan — Tier 1 Closeout"
type: test-plan
sprint: 3
last_updated: 2026-04-18
status: approved-pending-user
supersedes: "./test-plan-v1-archived.md"
---

# Sprint 3 Test Plan

Given/When/Then coverage for the trimmed Sprint 3 scope. pytest answers "does the code work?" (developer perspective). `adk eval` answers "does the agent give the right answer?" (user perspective). Both required.

---

## 1. Unit tests (pytest, `tests/unit/`)

### 1.1 Pipeline callbacks — `tests/unit/triage/test_pipeline_callbacks.py`

| # | Given / When / Then |
|---|---|
| U-1 | Given raw text "ghayal driver, ambulance needed" → When Rule B callback fires → Then callback returns escalation Content, `triage:classification.severity=="CRITICAL"`, `triage:classification.safety_escalation` populated, `triage:skip_impact=True` |
| U-2 | Given raw text "accident ho gaya" (Hinglish) → When Rule B callback fires → Then escalation Content returned (NFKC + casefold match) |
| U-3 | Given raw text "shipment late" → When Rule B callback fires → Then returns `None` (pipeline proceeds) |
| U-4 | Given classification `exception_type="regulatory_compliance"`, `severity="LOW"` → When Rule C/F callback on Impact fires → Then returns `None` (Rule C overrides Rule F, Impact runs) |
| U-5 | Given classification `exception_type="carrier_capacity_failure"`, `severity="LOW"` → When Rule C/F callback fires → Then returns skip Content with `impact=None` marker, `triage:skip_impact=True` |
| U-6 | Given classification `severity="HIGH"` → When Rule C/F callback fires → Then returns `None` (Impact runs) |
| U-7 | Given `triage:skip_impact=True` already set by Rule B → When Rule C/F callback on Impact fires → Then still skips (defense in depth) |
| U-8 | Given classification with `exception_type="customer_escalation"`, `severity="MEDIUM"` → When Rule C/F callback fires → Then returns `None` |
| U-9 | Conflict test: safety + regulatory + LOW → Rule B callback wins → short-circuits before Classifier. Impact callback never invoked. |
| U-10 | Safety keyword list fuzz: run 30 adversarial strings (leetspeak, mixed-case, unicode homoglyphs). Assert expected match/no-match per case. |

### 1.2 Pipeline factory — `tests/unit/triage/test_pipeline_factory.py`

| # | Given / When / Then |
|---|---|
| U-11 | Given factory called → When pipeline is constructed → Then returns `SequentialAgent` with exactly 2 sub-agents in order [classifier, impact] |
| U-12 | Classifier sub-agent has `before_agent_callback` pointing at Rule B function |
| U-13 | Impact sub-agent has `before_agent_callback` pointing at Rule C/F function |

### 1.3 Runner — `tests/unit/runners/test_triage_runner.py`

| # | Given / When / Then |
|---|---|
| U-14 | Given blocking call with `event_id` → When runner executes → Then seeds session state with `triage:event` from Firestore, invokes pipeline, returns assembled `TriageResult`, closes session on success |
| U-15 | Given blocking call raises mid-pipeline → When runner catches → Then closes session in `try/finally`, returns partial `TriageResult` with `status="partial"` |
| U-16 | Given streaming call → When runner yields → Then emits events in order: `agent_started` → `tool_invoked`+ → `agent_completed` → `partial_result` → `agent_started` → `tool_invoked`+ → `agent_completed` → `complete` → `done` |
| U-17 | Given client disconnect mid-stream → When runner detects `asyncio.CancelledError` → Then cancels the ADK driver, closes session, no further events emitted |
| U-18 | Given Impact raises `ImpactTransientError` → When tenacity wrapper catches → Then retries once, if still fails returns partial TriageResult |

### 1.4 API routes — `tests/unit/runners/routes/`

| # | Given / When / Then |
|---|---|
| U-19 | `POST /api/v1/triage` — happy: body `{event_id: "EXC-001"}` + auth bearer → 200, `text/event-stream`, expected frame sequence |
| U-20 | `POST /api/v1/triage` — missing auth → 401 |
| U-21 | `POST /api/v1/triage` — wrong tenant (event belongs to other company) → 403 |
| U-22 | `POST /api/v1/triage` — missing body or both `event_id` and `raw_content` → 422 |
| U-23 | `POST /api/v1/triage` — over 10/min from same IP → 429 |
| U-24 | `GET /api/v1/exceptions` — happy, page 1, tenant-scoped → 200, `Page[ExceptionPublic]` |
| U-25 | `GET /api/v1/exceptions` — cursor round-trip (page 2) → 200, no duplicates |
| U-26 | `POST /api/v1/auth/onboard` — new user → 200, claims set, response says `requires_token_refresh=true` |
| U-27 | `POST /api/v1/auth/onboard` — existing user → idempotent 200, claims unchanged |

### 1.5 Firestore rules — `tests/unit/firestore/test_rules.py` (emulator-based)

| # | Given / When / Then |
|---|---|
| U-28 | Read `routes/{id}` as same-tenant member → allowed |
| U-29 | Read `routes/{id}` as different tenant → denied |
| U-30 | Read `hubs/{id}` as same-tenant → allowed; as different tenant → denied |
| U-31 | Write `triage_results/{id}` as client → denied (Admin SDK only) |
| U-32 | Write `audit_events/{id}` as client → denied |
| U-33 | Catch-all deny: write `/unknown_collection/x` → denied even as authed user |

### 1.6 Tool / tenant-leak regression — `tests/unit/triage/tools/test_impact_tools.py`

| # | Given / When / Then |
|---|---|
| U-34 | Given 5 shipments across 2 tenants → When `get_affected_shipments` called with `company_id="comp_A"` → Then returns only `comp_A` shipments |
| U-35 | Fuzz: `company_id` param omitted → Then raises or returns `[]` (fail-closed) |

---

## 2. Integration tests (`tests/integration/`, emulator-dependent, `@pytest.mark.integration`)

### 2.1 Full pipeline — `tests/integration/test_triage_pipeline.py`

| # | Given / When / Then |
|---|---|
| I-1 | **NH-48 flagship**: Firestore emulator seeded via `seed_all.py` → invoke `TriageRunner.run(event_id=NH48)` → `status="complete"`, `classification.severity="CRITICAL"`, `impact.critical_path_shipment_id="SHP-2024-4821"`, `audit_events/{id}` written, `triage_results/{id}` written |
| I-2 | **Safety override (Hinglish)**: "accident ho gaya NH-48 pe" raw text → `status="escalated_to_human_safety"`, Classifier NOT invoked (monkeypatched to raise), Impact NOT invoked, audit event emitted |
| I-3 | **Regulatory LOW (Rule C)**: event classified as regulatory_compliance + LOW → Impact IS invoked, final `status="complete"`, `impact` populated |
| I-4 | **LOW non-regulatory skip (Rule F)**: severity="LOW", exception_type="customer_escalation" → Impact NOT invoked, final `impact=None`, `status="complete"` |
| I-5 | **Impact failure with retry**: Firestore returns transient error on first call → tenacity retries once → succeeds → final `status="complete"` |
| I-6 | **Impact failure after retry**: Firestore still fails → final `status="partial"`, `classification` populated, `impact=None`, error logged |
| I-7 | **Tenant isolation**: seed 2 tenants; run pipeline as tenant A → never reads tenant B's data |

### 2.2 SSE — `tests/integration/test_triage_sse.py`

| # | Given / When / Then |
|---|---|
| I-8 | Stream the NH-48 pipeline → frames in order: `agent_started(classifier)`, multiple `tool_invoked`, `agent_completed(classifier)`, `partial_result`, `agent_started(impact)`, multiple `tool_invoked`, `agent_completed(impact)`, `complete`, `done` |
| I-9 | Stream with safety override → frames: `agent_started(classifier)`, `agent_completed(classifier)` with placeholder, `complete` with escalated status, `done` — no Impact frames |
| I-10 | Client cancels stream mid-flight → connection closes, no further frames, session cleaned up (assert via log inspection) |
| I-11 | Heartbeat: no event for 15s → SSE `:` comment frame emitted |

### 2.3 Auth — `tests/integration/test_auth_onboard.py`

| # | Given / When / Then |
|---|---|
| I-12 | Mint Firebase emulator token → `POST /api/v1/auth/onboard` → verify user doc written to Firestore, custom claim set, response shape correct |
| I-13 | Call `/auth/onboard` twice same uid → both 200, no duplicate user doc |
| I-14 | Force token refresh → new token has `company_id` claim → subsequent `/api/v1/triage` call succeeds |
| I-15 | Rate limit on `/auth/onboard`: 6th call/min from same IP → 429 |

---

## 3. Evalsets (`adk eval`, `evals/`)

### 3.1 Classifier — `evals/classifier/evalset.json` (15 cases)

**6 happy:** one per `exception_type` (carrier_capacity_failure / customer_escalation / regulatory_compliance / external_disruption / documentation_issue / route_disruption). All English, clear severity signal.

**4 edge:** low-confidence ambiguous text, minimal input ("shipment late"), mixed-signal (customer escalation + weather), truncated raw_content.

**3 safety (Rule B):** NH-48 Hinglish ("ghayal ho gaya driver"), English explicit ("driver injured, ambulance en route"), Hindi transliterated ("durghatna ho gayi, hospital").

**2 adversarial:** prompt-injection attempt ("ignore prior instructions..."), adversarial severity flip ("URGENT!!! but actually routine delivery window adjustment").

Pass threshold: **≥13/15** (`tool_trajectory_avg_score ≥ 0.9`, `rubric_based_final_response_quality_v1 ≥ 0.8`).

### 3.2 Impact — `evals/impact/evalset.json` (10 cases)

**5 happy:** various severities + exception types with full shipment/customer/route graph → assert `critical_path_shipment_id`, `recommended_priority_order`, `impact_weights_used`.

**2 skip-cases:** Rule F (LOW non-regulatory) and Rule C (regulatory LOW) — assert callback fires correctly.

**2 edge:** multi-customer ripple (2+ customers affected), empty-shipment (no affected shipments, graceful empty result).

**1 failure:** Firestore `NotFound` on a referenced route → tool returns `{"status":"error", ...}` → Impact handles gracefully → final result has `impact=None` or partial data.

Pass threshold: **≥8/10**.

---

## 4. Smoke tests (manual)

| # | Step | Expected |
|---|---|---|
| S-1 | `adk web src/.../modules/triage/pipeline` → paste NH-48 → watch output | Full pipeline runs, structured result correct |
| S-2 | Seeded emulator → `uv run python -m supply_chain_triage.runners.triage_runner --event EXC-NH48` | Returns TriageResult JSON |
| S-3 | `curl -N -H "Authorization: Bearer $TOKEN" -X POST localhost:8080/api/v1/triage -d '{"event_id":"EXC-NH48"}'` | SSE stream with expected frames |
| S-4 | Judge flow on staging URL: sign in → console → run NH-48 → see streaming → see TriageResult card → navigate to History → see the run | All screens work end-to-end |
| S-5 | Apr 27 full dress: same as S-4 on prod URL with min-instances=1, 3 scenarios run | All 3 pass within ~10s each, no 429s, no errors in logs |

---

## 5. Evalset config — `evals/test_config.json`

```json
{
  "criteria": {
    "tool_trajectory_avg_score": 0.9,
    "rubric_based_final_response_quality_v1": 0.8
  },
  "num_runs": 3
}
```

`num_runs=3` mitigates LLM nondeterminism — a case passes if the majority of 3 runs pass.

---

## 6. CI integration

- Unit tests + integration tests run on every push (existing `.github/workflows/ci.yml`).
- Evalsets run nightly (not per-PR — they hit live Gemini).
- Add: `uv run lint-imports` step (if not already) to keep architecture-layer contracts green.

---

## 7. What we're NOT testing

- Coordinator `LlmAgent` eval (no Coordinator, no eval — by design).
- SSE reconnection via `Last-Event-ID` (stateless for Tier 1).
- Multi-turn conversations (single-turn only Tier 1).
- Supermemory integration (Tier 2).
- Token-stream events (Tier 2).
- Cross-region failover (single region asia-south1).

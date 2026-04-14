---
title: "Sprint 2 Test Plan — Impact Agent"
type: deep-dive
domains: [supply-chain, hackathon, sdlc, testing]
last_updated: 2026-04-10
status: active
confidence: high
sources: ["[[Supply-Chain-Agent-Spec-Impact]]", "[[Supply-Chain-Firestore-Schema-Tier1]]"]
---

# Sprint 2 Test Plan — Impact Agent

> **Companion to:** `prd.md` sections 4 (Acceptance Criteria) and 5 (Test Cases)
> **Format:** Given / When / Then for every scenario.
> **Target coverage:** >= 85% on all Sprint 2 modules.
> **Total test count:** >= 45 (unit + integration + eval).

---

## Table of Contents

1. [Test Pyramid Layout](#1-test-pyramid-layout)
2. [Fixtures and Test Infrastructure](#2-fixtures-and-test-infrastructure)
3. [Unit Tests — Tools](#3-unit-tests--tools)
4. [Unit Tests — Memory](#4-unit-tests--memory)
5. [Unit Tests — Guardrails](#5-unit-tests--guardrails)
6. [Unit Tests — Agent](#6-unit-tests--agent)
7. [Integration Tests — Firestore Emulator](#7-integration-tests--firestore-emulator)
8. [Integration Tests — Multi-Tenant Isolation](#8-integration-tests--multi-tenant-isolation)
9. [Integration Tests — Firestore Rules](#9-integration-tests--firestore-rules)
10. [Integration Tests — Seed Idempotency](#10-integration-tests--seed-idempotency)
11. [Integration Tests — AgentEvaluator](#11-integration-tests--agentevaluator)
12. [Eval Cases — impact_eval.json](#12-eval-cases--impact_evaljson)
13. [Coverage Targets](#13-coverage-targets)
14. [Manual Smoke Test Checklist](#14-manual-smoke-test-checklist)
15. [Flaky Test Policy](#15-flaky-test-policy)

---

## 1. Test Pyramid Layout

```
                     +-----------------------+
                     |   Manual adk web      |    1 scenario (NH-48)
                     |   smoke tests         |
                     +-----------------------+
                    +-------------------------+
                    |  Integration tests       |   ~8 tests
                    |  (emulator, rules, eval) |
                    +-------------------------+
                 +---------------------------+
                 |      Unit tests             |  ~38 tests
                 |  (tools, memory, guardrails,|
                 |   agent, sanity validator)  |
                 +---------------------------+
```

Sprint 2 follows the Sprint 1 pattern: heavy unit coverage (fast, deterministic) with a thinner integration layer that validates the Firestore + LLM end-to-end path. The eval layer is where LLM non-determinism is tolerated (pin `temperature=0`; rubric-based match).

---

## 2. Fixtures and Test Infrastructure

### 2.1 `tests/conftest.py` — new fixtures added this sprint

```python
import os
import asyncio
import pytest
import pytest_asyncio
import firebase_admin
from firebase_admin import firestore_async
from freezegun import freeze_time

from supply_chain_triage.memory.provider import StubMemoryProvider

# CRITICAL C2: seed shipments carry hardcoded deadlines of 2026-04-11 →
# 2026-04-13. Sprint 2 executes Apr 14-15, so without freezing time all
# deadlines would be in the past, making `hours_until_deadline` negative
# and flipping every shipment to CRITICAL — breaking AC #11 (priority
# reasoning must cite a 19-hour campaign deadline for BlushBox).
#
# We freeze system time at 2026-04-10T14:15:00+05:30 — the canonical
# "now" that matches the demo scenario's 19hr-to-BlushBox-deadline math.
# All tests that depend on relative deadline arithmetic must run under
# this freeze window.
_CANONICAL_NOW = "2026-04-10T14:15:00+05:30"


@pytest_asyncio.fixture(scope="session")
async def firestore_emulator():
    """Boot a Firestore emulator for the test session.

    Assumes `firebase emulators:start --only firestore` is already running
    on localhost:8080, or will skip with a clear message.
    """
    if "FIRESTORE_EMULATOR_HOST" not in os.environ:
        os.environ["FIRESTORE_EMULATOR_HOST"] = "localhost:8080"

    if not firebase_admin._apps:
        firebase_admin.initialize_app(options={"projectId": "demo-supply-chain-triage"})

    client = firestore_async.client()
    yield client


@pytest_asyncio.fixture(scope="function")
async def firestore_emulator_seeded(firestore_emulator):
    """Clear + seed the emulator under a frozen system clock.

    Per-function scope guarantees each test sees a clean NH-48 dataset
    AND a deterministic "now" of 2026-04-10T14:15:00+05:30, so deadline
    math is reproducible across Sprint 2 test runs regardless of
    wall-clock date.
    """
    with freeze_time(_CANONICAL_NOW):
        client = firestore_emulator
        # Clear existing
        for col_name in ["companies", "customers", "shipments", "exceptions"]:
            async for doc in client.collection(col_name).stream():
                await doc.reference.delete()

        # Seed fresh — canonical Apr-10 base time is active
        from scripts.seed_firestore_shipments import _seed_collection
        await _seed_collection("companies")
        await _seed_collection("customers")
        await _seed_collection("shipments")

        yield client


@pytest.fixture
def stub_memory_provider():
    """Return a StubMemoryProvider for unit tests."""
    return StubMemoryProvider()


@pytest.fixture
def mock_tool_context(stub_memory_provider):
    """Create a fake ToolContext with populated session state."""
    from unittest.mock import MagicMock
    ctx = MagicMock()
    ctx.state = {
        "company_id": "comp_nimblefreight",
        "user_id": "user_priya_001",
        "memory_provider": stub_memory_provider,
    }
    return ctx
```

### 2.2 Fake Firestore fallback

Where the emulator is unavailable (offline CI), a fallback fixture uses `mock-firestore-async` to provide an in-memory double. This is a fallback only — the primary path is the real emulator.

---

## 3. Unit Tests — Tools

### 3.1 `tests/unit/tools/test_firestore_shipments.py`

#### Test 3.1.1 — `test_get_by_vehicle_happy_path`

**Given** the emulator is seeded with 4 shipments on `MH-04-XX-1234` (all `company_id=comp_nimblefreight`, status `in_transit`) and 5 distractor shipments on other vehicles.
**When** we call `await get_active_shipments_by_vehicle("MH-04-XX-1234", tool_context=mock_ctx)` with `company_id=comp_nimblefreight` in session state.
**Then** the return is a list of length 4 containing shipment IDs `{SHP-2024-4821, SHP-2024-4822, SHP-2024-4823, SHP-2024-4824}`, every record has `status=in_transit`, and no distractors appear.

#### Test 3.1.2 — `test_get_by_vehicle_wrong_company_returns_empty`

**Given** the emulator is seeded with NH-48 shipments under `comp_nimblefreight`.
**When** we call the tool with `company_id=comp_ghost` in session state.
**Then** the return is an empty list `[]`. No `PermissionError` is raised (company was provided, just no matching data).

#### Test 3.1.3 — `test_get_by_vehicle_missing_company_raises`

**Given** `mock_tool_context.state` has no `company_id` key.
**When** we call `get_active_shipments_by_vehicle`.
**Then** `PermissionError` is raised with message containing `"company_id missing from session state"`.

#### Test 3.1.4 — `test_get_by_route_single_match`

**Given** the emulator has 6 shipments on `ROUTE-MUM-PUNE-01` across 2 vehicles (the NH-48 4 + 2 more from hypothetical seed extension).
**When** we call `get_active_shipments_by_route("ROUTE-MUM-PUNE-01")`.
**Then** the return length is 4 in Sprint 2 baseline (NH-48 only route shipments on this route).

#### Test 3.1.5 — `test_get_by_region_monsoon_scenario`

**Given** the emulator has shipments across `maharashtra_west` (4 NH-48 + 2 distractors = 6) and `karnataka_north` (2) and `gujarat_south` (1).
**When** we call `get_active_shipments_by_region("maharashtra_west")`.
**Then** the return length is 6 (4 NH-48 + 2 distractors on the same region but different vehicles).

#### Test 3.1.6 — `test_get_shipment_details_found`

**Given** the emulator has `SHP-2024-4821` seeded with full BlushBox payload.
**When** we call `get_shipment_details("SHP-2024-4821")`.
**Then** the return is a dict containing `customer_id=cust_blushbox`, `value_inr=850000`, `public_facing_deadline=True`, `vehicle_id=MH-04-XX-1234`.

#### Test 3.1.7 — `test_get_shipment_details_not_found_returns_none`

**Given** the emulator has no document with ID `SHP-9999-9999`.
**When** we call `get_shipment_details("SHP-9999-9999")`.
**Then** the return is `None`. No exception raised.

#### Test 3.1.8 — `test_get_shipment_details_cross_tenant_returns_none`

**Given** `SHP-2024-4821` exists under `comp_nimblefreight`.
**When** we call `get_shipment_details("SHP-2024-4821")` with `company_id=comp_rival`.
**Then** the return is `None` — the tool-layer guard matches the document's `company_id` field to the session state `company_id`.

#### Test 3.1.9 — `test_gather_concurrency_under_wallclock_threshold`

**Given** 4 shipment IDs that each take ~100 ms individually (measured via emulator).
**When** we call `_get_shipments_bulk(ids)` (private helper; not exposed to the LLM) which uses `asyncio.gather`.
**Then** the wall-clock elapsed time is < 240 ms (roughly sum-of-4 x 0.6 = 240), proving concurrent execution. Individual sequential fetches would take > 400 ms.

#### Test 3.1.10 — `test_status_filter_excludes_delivered`

**Given** the emulator has `SHP-2024-5002` with `status="delivered"` on `MH-14-CD-5544`.
**When** we call `get_active_shipments_by_vehicle("MH-14-CD-5544")`.
**Then** `SHP-2024-5002` is NOT in the result — only `in_transit` shipments are returned.

#### Test 3.1.11 — `test_no_company_id_in_tool_signature`

**Given** we inspect the function signature of `get_active_shipments_by_vehicle` via `inspect.signature()`.
**When** we list the parameter names.
**Then** `company_id` is NOT in the parameter list — only `vehicle_id` and `tool_context`. This is a signature-level guard against prompt injection.

#### Test 3.1.12 — `test_latency_p95_under_500ms`

**Given** the emulator is warm.
**When** we call `get_active_shipments_by_vehicle` 20 times and measure per-call latency.
**Then** the p95 latency is < 500 ms (emulator baseline).

### 3.2 `tests/unit/tools/test_firestore_customers.py`

#### Test 3.2.1 — `test_get_customer_profile_found`

**Given** `cust_blushbox` is seeded under `comp_nimblefreight`.
**When** we call `get_customer_profile("cust_blushbox")`.
**Then** the return dict contains `customer_tier=high_value`, `customer_type=d2c`, `churn_risk_score=0.7`, `relationship_value_inr=5000000`.

#### Test 3.2.2 — `test_get_customer_profile_not_found_returns_none`

**Given** no document exists for `cust_missing`.
**When** we call `get_customer_profile("cust_missing")`.
**Then** return is `None`.

#### Test 3.2.3 — `test_cross_tenant_customer_returns_none`

**Given** `cust_blushbox` under `comp_nimblefreight`.
**When** we call with `company_id=comp_rival`.
**Then** return is `None`.

#### Test 3.2.4 — `test_field_presence_tier_churn_ltv`

**Given** a minimal customer record with all required fields.
**When** we fetch.
**Then** result has exactly these top-level keys: `customer_id`, `company_id`, `name`, `customer_type`, `customer_tier`, `relationship_value_inr`, `churn_risk_score`.

#### Test 3.2.5 — `test_missing_optional_fields_handled`

**Given** `cust_trektech` which has no `historical_metrics` field in the seed.
**When** we fetch.
**Then** the result dict has no `historical_metrics` key but does not raise KeyError; the agent handles this gracefully downstream.

#### Test 3.2.6 — `test_p95_latency_under_500ms`

**Given** the emulator is warm.
**When** we call `get_customer_profile` 20 times.
**Then** p95 < 500 ms.

### 3.3 `tests/unit/tools/test_memory_tools.py`

#### Test 3.3.1 — `test_lookup_history_with_stub_returns_empty_list`

**Given** `tool_context.state["memory_provider"] = StubMemoryProvider()`.
**When** we call `await lookup_customer_exception_history("cust_blushbox", tool_context, limit=5)`.
**Then** return is `[]`.

#### Test 3.3.2 — `test_missing_provider_raises_runtime_error`

**Given** `tool_context.state` has no `memory_provider` key.
**When** we call the tool.
**Then** `RuntimeError` is raised with message mentioning `"memory_provider missing from session state"`.

#### Test 3.3.3 — `test_wrong_type_provider_raises_type_error`

**Given** `tool_context.state["memory_provider"] = "not a provider"`.
**When** we call the tool.
**Then** `TypeError` is raised with message mentioning `MemoryProvider`.

---

## 4. Unit Tests — Memory

### 4.1 `tests/unit/memory/test_stub_adapter.py`

#### Test 4.1.1 — `test_lookup_customer_exception_history_returns_empty`

**Given** a fresh `StubMemoryProvider()`.
**When** we call `await provider.lookup_customer_exception_history("cust_any", limit=5)`.
**Then** return is `[]`.

#### Test 4.1.2 — `test_lookup_similar_past_exceptions_returns_empty`

**Given** a fresh `StubMemoryProvider()`.
**When** we call `await provider.lookup_similar_past_exceptions("any context", limit=3)`.
**Then** return is `[]`.

#### Test 4.1.3 — `test_implements_memory_provider_abc`

**Given** `StubMemoryProvider`.
**When** we check `isinstance(StubMemoryProvider(), MemoryProvider)`.
**Then** `True`.

#### Test 4.1.4 — `test_is_pickleable`

**Given** a fresh `StubMemoryProvider()`.
**When** we `pickle.dumps(provider)` and `pickle.loads(...)`.
**Then** the round-trip succeeds (required for ADK session state serialization fallback).

### 4.2 `tests/unit/memory/test_supermemory_adapter.py`

All tests use `unittest.mock.patch("supermemory.Supermemory")` to avoid hitting the real API.

#### Test 4.2.1 — `test_happy_path_customer_history`

**Given** the mocked `Supermemory` client returns a response with 3 results.
**When** we instantiate `SupermemoryAdapter(api_key="test", company_id="comp_nimblefreight")` and call `lookup_customer_exception_history("cust_blushbox", limit=5)`.
**Then** return length is 3, each item is a `PastException` model instance, and the mock was called with `q="exceptions involving customer cust_blushbox"`.

#### Test 4.2.2 — `test_happy_path_similar_exceptions`

**Given** mocked client returns 2 results.
**When** we call `lookup_similar_past_exceptions("truck breakdown NH-48", limit=3)`.
**Then** return length is 2; mock was called with the context string as `q`.

#### Test 4.2.3 — `test_sdk_error_returns_empty_and_logs`

**Given** mocked client raises `RuntimeError("network down")` on call.
**When** we call `lookup_customer_exception_history("cust_x")`.
**Then** return is `[]`; a log record with event `memory.error` is captured via `caplog`; no exception propagates.

#### Test 4.2.4 — `test_container_tags_scoping`

**Given** we instantiate with `company_id="comp_nimblefreight"`.
**When** we call `lookup_customer_exception_history("cust_blushbox")`.
**Then** the mock was called with `container_tags=["company:comp_nimblefreight", "customer:cust_blushbox"]` — asserted via `mock.call_args`.

#### Test 4.2.5 — `test_respects_limit_parameter`

**Given** we call with `limit=2`.
**When** the mock is invoked.
**Then** the mock receives `limit=2` — verified via `mock.call_args.kwargs["limit"]`.

#### Test 4.2.6 — `test_missing_api_key_raises_value_error`

**Given** no `SUPERMEMORY_API_KEY` env var and no explicit `api_key` argument.
**When** we instantiate `SupermemoryAdapter(company_id="comp_x")`.
**Then** `ValueError` with message containing `"SUPERMEMORY_API_KEY not set"`.

---

## 5. Unit Tests — Guardrails

### 5.1 `tests/unit/guardrails/test_impact_validators.py`

For these tests, we create valid NH-48 `ImpactResult` objects and mutate one invariant at a time.

#### Test 5.1.1 — `test_happy_path_canonical_nh48_passes`

**Given** a canonical NH-48 `ImpactResult` with 4 shipments, correct priority order, matching totals, and consistent reputation flags.
**When** we call `impact_sanity_check(result)`.
**Then** returns the result unchanged; no exception.

#### Test 5.1.2 — `test_critical_path_not_in_priority_order_raises`

**Given** result has `critical_path_shipment_id="SHP-2024-4821"` but `recommended_priority_order` does not include `SHP-2024-4821`.
**When** we call `impact_sanity_check`.
**Then** `ImpactValidationError` with message containing `"critical_path_shipment_id"` and `"not in recommended_priority_order"`.

#### Test 5.1.3 — `test_priority_order_has_duplicate_raises`

**Given** `recommended_priority_order=["SHP-2024-4821", "SHP-2024-4821", "SHP-2024-4822", "SHP-2024-4823"]` — duplicate.
**When** we call.
**Then** `ImpactValidationError` with message containing `"not a permutation"`.

#### Test 5.1.4 — `test_priority_order_missing_shipment_raises`

**Given** priority order has 3 shipments but affected_shipments has 4.
**When** we call.
**Then** `ImpactValidationError` with `"not a permutation"`.

#### Test 5.1.5 — `test_total_value_mismatch_raises`

**Given** `total_value_at_risk_inr=1000000` but the sum of the 4 shipments is `1850000`.
**When** we call.
**Then** `ImpactValidationError` with message containing `"total_value_at_risk_inr"` and `"does not match"`.

#### Test 5.1.6 — `test_reputation_flag_mismatch_raises`

**Given** `has_reputation_risks=True` but `reputation_risk_shipments=[]`.
**When** we call.
**Then** `ImpactValidationError` with message containing `"has_reputation_risks"` and `"inconsistent"`.

#### Test 5.1.7 — `test_reputation_shipment_not_in_affected_raises`

**Given** `reputation_risk_shipments=["SHP-9999-UNKNOWN"]` but `affected_shipments` has only NH-48 IDs.
**When** we call.
**Then** `ImpactValidationError` with message containing `"not in affected_shipments"`.

#### Test 5.1.8 — `test_empty_result_passes`

**Given** `ImpactResult` with `affected_shipments=[]`, `total_value_at_risk_inr=0`, `critical_path_shipment_id=None` (see I6 empty-vehicle convention in `prd.md` §5), `has_reputation_risks=False`, `reputation_risk_shipments=[]`.
**When** we call `impact_sanity_check`.
**Then** returns unchanged; no exception (empty is valid).

#### Test 5.1.9 — `test_empty_result_with_non_none_critical_path_raises`

**Given** `ImpactResult` with `affected_shipments=[]` but `critical_path_shipment_id=""` (empty string — a common LLM mistake).
**When** we call `impact_sanity_check`.
**Then** `ImpactValidationError` with message containing `"critical_path_shipment_id must be None"`.

---

## 6. Unit Tests — Agent

### 6.1 `tests/unit/agents/test_impact.py`

#### Test 6.1.1 — `test_impact_agent_instantiates`

**Given** the `impact_agent` module is imported.
**When** we check `impact_agent.name`.
**Then** `impact_agent.name == "ImpactAgent"` and `impact_agent.model == "gemini-2.5-flash"`.

#### Test 6.1.2 — `test_tool_wiring_count_equals_7`

**When** we count `len(impact_agent.tools)`.
**Then** `== 7`.

#### Test 6.1.3 — `test_tool_names_match_expected`

**When** we extract `[t.__name__ for t in impact_agent.tools]`.
**Then** the set equals `{get_active_shipments_by_vehicle, get_active_shipments_by_route, get_active_shipments_by_region, get_shipment_details, get_customer_profile, lookup_customer_exception_history, lookup_similar_past_exceptions}`.

#### Test 6.1.4 — `test_prompt_structural_blocks`

**Given** the `impact.md` prompt file is loaded.
**When** we search for XML tag markers.
**Then** all of these are present: `<role>`, `<architectural_rules>`, `<workflow>`, `<impact_calculation>`, `<priority_rules>`, `<rule_e>`, `<few_shot_examples>`. File size < 15 KB.

#### Test 6.1.5 — `test_output_key_and_after_agent_callback_wired`

**When** we inspect `impact_agent`.
**Then**:
- `impact_agent.output_key == "impact_result"` (NOT `output_schema` — ADK forbids combining `output_schema` with `tools`; tools would be silently suppressed)
- `impact_agent.output_schema is None`
- `impact_agent.after_agent_callback is _after_impact_validate`

#### Test 6.1.6 — `test_impact_sanity_check_is_wired_in_callback`

**Given** `guardrails.impact_validators`.
**When** we import `impact_sanity_check` AND invoke `_after_impact_validate` with a `CallbackContext` whose state contains a canonical NH-48 `impact_result` dict.
**Then** after the callback runs, `state["impact_result"]` is a validated dict that round-trips through `ImpactResult.model_validate()` and passes `impact_sanity_check` unchanged. (Sprint 2 wires the validator into the agent; Sprint 3 Coordinator may layer an additional `after_model_callback` re-ask via Guardrails if needed.)

---

## 7. Integration Tests — Firestore Emulator

### 7.1 `tests/integration/test_impact_firestore_emulator.py`

#### Test 7.1.1 — `test_impact_agent_nh48_4_shipments`

**Given** the Firestore emulator is seeded with the 4 NH-48 shipments + 5 distractors + 4 customers (under frozen time `2026-04-10T14:15:00+05:30`), and session state contains `company_id=comp_nimblefreight`, `memory_provider=StubMemoryProvider()`, an `exception_event` dict with `event_id="evt_001"` + `source_channel="whatsapp_voice"` + `sender`, and a canned NH-48 `classification` dict.
**When** we invoke `impact_agent` via `InMemoryRunner.run_async()` with message "Assess the impact of the classified exception."
**Then** the final response parses as `ImpactResult` JSON with:
- `event_id == "evt_001"` (copied verbatim from `exception_event.event_id`; see C1/C3)
- `len(affected_shipments) == 4`
- `total_value_at_risk_inr == 1850000`
- `critical_path_shipment_id == "SHP-2024-4821"`
- `has_reputation_risks is True`
- `"SHP-2024-4821" in reputation_risk_shipments`
- `"SHP-2024-4823" in reputation_risk_shipments`
- `recommended_priority_order[0] == "SHP-2024-4821"`
- `"get_active_shipments_by_vehicle" in tools_used` (I1 — guards against silent tool suppression from output_schema+tools conflict)
- `len(tools_used) >= 2` (at minimum vehicle lookup + customer profile)
- `impact_weights_used` contains three weights summing to `1.0 +/- 0.02`
- `impact_weights_used.reasoning` is non-empty
- `priority_reasoning` non-empty and contains one of `{BlushBox, 19, campaign, deadline}` (case-insensitive regex)
- Elapsed wall-clock < 10 s

#### Test 7.1.2 — `test_impact_agent_empty_vehicle`

**Given** the emulator is seeded but we target `vehicle_id="MH-99-XX-0000"` which has zero shipments.
**When** we run the agent.
**Then** `affected_shipments == []`, `total_value_at_risk_inr == 0`, `has_reputation_risks is False`, `critical_path_shipment_id is None` (I6 convention — NOT empty string), `event_id == "evt_001"` (copied verbatim from `exception_event`), `summary` non-empty describing the empty result.

#### Test 7.1.3 — `test_impact_agent_route_disruption`

**Given** emulator has 4 NH-48 shipments on `ROUTE-MUM-PUNE-01`, and classification key_facts has only `route_id` (no `vehicle_id`).
**When** we run.
**Then** the agent calls `get_active_shipments_by_route` (not `_by_vehicle`), returns the 4 shipments, same totals as NH-48 case.

#### Test 7.1.4 — `test_impact_agent_region_monsoon`

**Given** emulator has 6 shipments in `maharashtra_west` (4 NH-48 + 2 distractors).
**When** classification has only `region=maharashtra_west` in key_facts.
**Then** the agent calls `get_active_shipments_by_region`, returns 6 shipments.

---

## 8. Integration Tests — Multi-Tenant Isolation

### 8.1 `tests/integration/test_impact_multi_tenant_isolation.py`

#### Test 8.1.1 — `test_nimblefreight_sees_only_own_shipments`

**Given** the emulator is seeded with:
- `comp_nimblefreight` has 4 shipments on `MH-04-XX-1234` (the NH-48 set)
- `comp_rival` has 4 DIFFERENT shipments on the SAME `MH-04-XX-1234` (rival's trucks use same plate format — theoretical collision)

**When** we run `impact_agent` with `session_state.company_id=comp_nimblefreight` and classification targeting `MH-04-XX-1234`.
**Then** the agent returns exactly the 4 NimbleFreight shipments; no Rival shipment IDs appear anywhere in the output.

#### Test 8.1.2 — `test_rival_sees_only_own_shipments`

**Given** same seed as 8.1.1.
**When** we run under `company_id=comp_rival`.
**Then** the agent returns exactly the 4 Rival shipments; no NimbleFreight IDs leak.

#### Test 8.1.3 — `test_cross_tenant_shipment_details_returns_none`

**Given** `SHP-2024-4821` belongs to `comp_nimblefreight`.
**When** we directly call `get_shipment_details("SHP-2024-4821")` with `company_id=comp_rival` in session state.
**Then** return is `None`.

#### Test 8.1.4 — `test_cross_tenant_customer_profile_returns_none`

**Given** `cust_blushbox` belongs to `comp_nimblefreight`.
**When** we call `get_customer_profile("cust_blushbox")` with `company_id=comp_rival`.
**Then** return is `None`.

---

## 9. Integration Tests — Firestore Rules

### 9.1 `tests/integration/test_firestore_rules.py`

Run via `firebase emulators:exec 'pytest tests/integration/test_firestore_rules.py'` so the rules layer is loaded.

#### Test 9.1.1 — `test_cross_tenant_read_denied`

**Given** two minted ID tokens:
- Token A: `{"uid": "user_a", "company_id": "comp_nimblefreight"}`
- Token B: `{"uid": "user_b", "company_id": "comp_rival"}`

**When** Token B attempts to read `shipments/SHP-2024-4821` (which belongs to `comp_nimblefreight`).
**Then** the Firestore rules layer returns a permission-denied error.

#### Test 9.1.2 — `test_same_tenant_read_allowed`

**When** Token A reads `shipments/SHP-2024-4821`.
**Then** read succeeds with the expected document.

#### Test 9.1.3 — `test_missing_company_claim_denied`

**Given** a token with NO `company_id` custom claim (only `uid`).
**When** it attempts any shipment read.
**Then** denied by the rules (the `isCompanyMember` function requires `company_id != null`).

#### Test 9.1.4 — `test_delete_always_denied`

**Given** Token A (legitimate NimbleFreight user).
**When** it attempts `delete` on `shipments/SHP-2024-4821`.
**Then** denied — our rules forbid deletes entirely (`allow delete: if false`).

#### Test 9.1.5 — `test_cross_tenant_where_query_denied`

**Given** Token B (`company_id=comp_rival`) and seeded data where `comp_nimblefreight` owns `SHP-2024-4821`.
**When** Token B issues a list query:
```python
client.collection("shipments").where("company_id", "==", "comp_rival").stream()
```
against the rules-enforcing emulator (a query that scans documents and returns only those matching).
**Then** the query returns zero documents for a non-existent tenant, AND — more importantly — a query that attempts to bypass the claim check by issuing `where("company_id", "==", "comp_nimblefreight")` with Token B is denied by the rules layer with a permission-denied error. Rationale (I7): rule evaluation under list/collection queries is subtly different from single-document `get()`. Rules apply per document returned, not to the query itself; Firestore denies the entire query if any returned document fails the rule. This test verifies that mismatched token-claim vs filter values are rejected at the rules layer, closing a subtle hole where a `where()` clause could otherwise scan across tenants if a dev accidentally removed the tool-layer guard.

---

## 10. Integration Tests — Seed Idempotency

### 10.1 `tests/integration/test_seed_idempotent.py`

#### Test 10.1.1 — `test_seed_twice_same_counts`

**Given** a fresh emulator with no seed data.
**When** we run `python scripts/seed_firestore_shipments.py` twice in succession.
**Then** after both runs, the emulator contains exactly 1 company + 6 customers + 9 shipments — no duplicates.

#### Test 10.1.2 — `test_seed_script_exit_code_zero`

**When** we run the seed script.
**Then** the process exits with code 0.

#### Test 10.1.3 — `test_seed_script_fails_on_partial_seed_files`

**Given** `scripts/seed/customers.json` is missing (simulated).
**When** we run the seed script.
**Then** the script logs a warning but continues; if total record count < 16, exits with code 1.

---

## 11. Integration Tests — AgentEvaluator

### 11.1 `tests/integration/test_impact_adk_eval.py`

#### Test 11.1.1 — `test_impact_eval_f1_at_least_80`

**Given** `tests/evals/impact_eval.json` is loaded (12 cases) and the emulator is seeded with data for each case's `initial_session_state`.
**When** we call `AgentEvaluator.evaluate(agent=impact_agent, eval_dataset_file_path_or_dir="tests/evals/impact_eval.json")`.
**Then** `result.metrics["final_response_match_v2"]["f1"] >= 0.80`.

#### Test 11.1.2 — `test_nh48_case_passes_with_high_score`

**Given** eval case `nh48_breakdown_4_shipments` (case #1).
**When** we evaluate just this case with `filter_eval_ids=["nh48_breakdown_4_shipments"]`.
**Then** the individual score is >= 0.90 (this is the few-shot case — should be near-perfect).

---

## 12. Eval Cases — impact_eval.json

The 12 eval cases in `tests/evals/impact_eval.json`:

| # | eval_id | Description | Expected shipment count | Notes |
|---|---------|-------------|-------------------------|-------|
| 1 | `nh48_breakdown_4_shipments` | Canonical NH-48 — must match few-shot exactly | 4 | Gate case |
| 2 | `single_shipment_vehicle` | Vehicle with only 1 active shipment | 1 | Edge: single-shipment priority is trivial |
| 3 | `route_disruption_6_shipments` | `route_id=ROUTE-MUM-PUNE-01` with 6 shipments across 2 vehicles | 6 | Tests route-scope tool selection |
| 4 | `region_monsoon_12_shipments` | `region=maharashtra_west` with 12 shipments | 12 | Tests region-scope + monsoon context |
| 5 | `empty_vehicle_zero_shipments` | `vehicle_id=MH-99-XX-0000` | 0 | Empty result graceful degradation |
| 6 | `all_b2b_low_reputation` | 3 B2B shipments, no public deadlines | 3 | `value_weight > churn_weight` expected |
| 7 | `all_d2c_diwali_festival` | 4 D2C shipments, all Diwali-related | 4 | `churn_weight + reputation` dominates |
| 8 | `mixed_with_penalty_clause` | 3 shipments, 1 has INR 5L penalty clause | 3 | `penalty_weight > 0.25` expected |
| 9 | `empty_supermemory_graceful` | Classification targeting new customer; stub returns `[]` | 1 | Agent must NOT call history tool repeatedly or loop |
| 10 | `cross_tenant_probe_empty` | Request with `company_id=comp_ghost` | 0 | Isolation check |
| 11 | `llm_inference_reputation` | Shipment with `public_facing_deadline=false` but description "Diwali sale launch" | 1 | `reputation_risk_source=="llm_inference"` |
| 12 | `priority_tiebreaker_identical_deadlines` | 2 shipments with identical deadline, one HIGH churn, one LOW | 2 | HIGH churn should come first in priority order |

Each case includes `initial_session_state`, `user_content`, `expected_tool_calls`, `expected_output_fields`, and a `metrics.final_response_match_v2.threshold=0.80`. The seeder runs `before_each_case` to load the case-specific data.

---

## 13. Coverage Targets

| Module | Target | Measurement |
|--------|--------|-------------|
| `agents/impact.py` | >= 85% | `pytest --cov=src/supply_chain_triage/agents/impact` |
| `tools/firestore_shipments.py` | 100% | `pytest --cov=...tools/firestore_shipments --cov-fail-under=100` |
| `tools/firestore_customers.py` | 100% | Same pattern |
| `tools/memory_tools.py` | 100% | Same pattern |
| `memory/provider.py` | 100% | ABC + Stub are small enough |
| `memory/supermemory_adapter.py` | >= 85% | Some error paths are hard to hit |
| `memory/stub_adapter.py` | 100% | Trivial |
| `guardrails/impact_validators.py` | 100% | Pure logic |

**Command:** `pytest --cov=src/supply_chain_triage --cov-report=term-missing --cov-report=html tests/`

---

## 14. Manual Smoke Test Checklist

Run once per day during Sprint 2 (end of Day 1 and end of Day 2):

- [ ] `firebase emulators:start --only firestore` running
- [ ] `python scripts/seed_firestore_shipments.py` succeeds, shows "Total records seeded: 16"
- [ ] `adk web` launches without error
- [ ] Paste a canned NH-48 `ClassificationResult` JSON via the `adk web` session state editor
- [ ] Trigger Impact Agent
- [ ] Response JSON contains all 4 NH-48 shipments, BlushBox first, reputation risks flagged
- [ ] Elapsed time < 5 s (Gemini network latency included)
- [ ] Screenshot captured into `impl-log.md`
- [ ] `make test` GREEN
- [ ] `make coverage` shows >= 85% on Sprint 2 modules
- [ ] `bandit -r src/supply_chain_triage/agents/impact.py tools/firestore_*.py memory/` has 0 HIGH findings
- [ ] `pre-commit run --all-files` GREEN

---

## 15. Flaky Test Policy

Integration + eval tests will occasionally flake due to Gemini non-determinism. Policy:

1. **Never retry silently.** If a test flakes, the CI pipeline marks it yellow.
2. **Rerun once manually.** If it passes on rerun, add to `tests/known_flaky.txt` with a dated note.
3. **Three flakes in one week → fix or quarantine.** Either pin a cassette, reduce rubric strictness, or move to `@pytest.mark.flaky` with `rerun=2` explicit.
4. **Eval threshold is 0.80, not 0.95.** This builds in headroom for LLM variance.
5. **All integration tests use `temperature=0`.** Sprint 1 pattern inherited.
6. **Pin Gemini model version.** `model="gemini-2.5-flash"` should be pinned to a stable snapshot ID if one exists, else accept drift and note in `risks.md`.
7. **No snapshot testing.** Do not compare raw LLM output strings; use structural assertions only.

---

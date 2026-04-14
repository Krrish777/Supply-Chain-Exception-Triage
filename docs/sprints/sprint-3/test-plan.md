---
title: "Sprint 3 Test Plan — Coordinator Agent + Full Pipeline"
type: deep-dive
domains: [supply-chain, hackathon, sdlc, testing]
last_updated: 2026-04-10
status: active
confidence: high
sources: ["./prd.md", "[[Supply-Chain-Agent-Spec-Coordinator]]", "[[Supply-Chain-Demo-Scenario-Tier1]]"]
---

# Sprint 3 Test Plan — Coordinator Agent (Full Pipeline Integration)

> **Companion to:** `./prd.md`
> **Sprint window:** Apr 16 – Apr 17, 2026
> **Scope:** Unit + Integration + Eval tests for the Coordinator agent, the `before_model_callback` context injection middleware, the `AgentRunner` portability layer, and the completed `MemoryProvider` / `SupermemoryAdapter`.

This file elaborates every Sprint 3 Acceptance Criterion into a **Given / When / Then** test case and maps each to its file + test function. An engineer unfamiliar with the codebase should be able to implement every test below from this document alone.

---

## Test Taxonomy

| Layer | Location | Runner | Dependencies |
|-------|----------|--------|--------------|
| **Unit — agent** | `tests/unit/agents/test_coordinator.py` | `pytest-asyncio` | FakeGeminiClient, InMemoryStubAdapter, patched sub-agents |
| **Unit — middleware** | `tests/unit/middleware/test_context_injection.py` | `pytest-asyncio` | InMemoryStubAdapter, mocked festival/monsoon tools |
| **Unit — memory** | `tests/unit/memory/test_provider_full_interface.py`, `test_supermemory_adapter_complete.py` | `pytest`, `pytest-asyncio` | Mocked `supermemory.Supermemory` SDK |
| **Unit — runners** | `tests/unit/runners/test_agent_runner.py` | `pytest-asyncio` | Mocked ADK `Runner` |
| **Integration — pipeline** | `tests/integration/test_coordinator_full_pipeline.py` | `pytest-asyncio` | Firestore emulator + real Classifier + real Impact + seeded stub adapter |
| **Integration — safety** | `tests/integration/test_coordinator_safety_override.py` | `pytest-asyncio` | Mocked sub-agents (assert NOT called) |
| **Integration — conflicts** | `tests/integration/test_coordinator_rule_conflicts.py` | `pytest-asyncio` | Mocked Classifier outputs |
| **Eval** | `tests/integration/test_coordinator_adk_eval.py` | `AgentEvaluator.evaluate()` | `tests/evals/coordinator_eval.json`, `test_config.json`, live Gemini 2.5 Flash |

---

## 1. Agent Instantiation & Wiring (AC #2, #3)

### TC-1.1 — Coordinator instantiates cleanly

**Given** the `supply_chain_triage.agents.coordinator` module
**When** we import `coordinator_agent`
**Then**
- `coordinator_agent.name == "ExceptionTriageCoordinator"`
- `coordinator_agent.model == "gemini-2.5-flash"`
- `len(coordinator_agent.description) >= 40`
- `coordinator_agent.output_key == "triage_result"`
- `coordinator_agent.instruction` is non-empty and contains `"Delegation Rules"`

**File**: `tests/unit/agents/test_coordinator.py::test_coordinator_instantiates`

### TC-1.2 — sub_agents wired with distinct descriptions

**Given** the Coordinator
**When** we inspect `coordinator_agent.sub_agents`
**Then**
- Exactly 2 sub-agents present: `{"ExceptionClassifier", "ExceptionImpactAnalyzer"}`
- Each has `description` length ≥ 40 chars
- Each has `sub_agents == []` (no recursion — specialists are leaves)
- The two descriptions share no 3-gram with > 50% overlap (distinctness for AutoFlow [ADK-MA])

**File**: `tests/unit/agents/test_coordinator.py::test_sub_agents_wired_with_descriptions`

### TC-1.3 — `before_model_callback` registered

**Given** the Coordinator
**When** we inspect `coordinator_agent.before_model_callback`
**Then** it `is` the `inject_dynamic_context` function from `supply_chain_triage.middleware.context_injection`

**File**: `tests/unit/agents/test_coordinator.py::test_before_model_callback_registered`

---

## 2. Rule A — WhatsApp Voice Urgency Hint (AC #4)

### TC-2.1 — Voice channel injects hint into runtime_context

**Given** an `ExceptionEvent` with `source_channel="whatsapp_voice"` and seeded session state `{user_id, company_id}`
**When** `AgentRunner.run_triage(event, ...)` is invoked
**Then**
- `inject_dynamic_context` emits an `audit_event("coordinator.context_injected", ..., voice_hint=True)`
- The mutated `system_instruction` contains the string `"Received via WhatsApp voice"`

**File**: `tests/unit/agents/test_coordinator.py::test_rule_a_whatsapp_voice_hint_in_context`

### TC-2.2 — Non-voice channel does NOT inject the hint

**Given** an `ExceptionEvent` with `source_channel="email"`
**When** the callback runs
**Then** `audit_event` kwargs have `voice_hint=False` and the `system_instruction` does NOT contain the voice hint string

**File**: `tests/unit/middleware/test_context_injection.py::test_rule_a_no_voice_hint_for_non_voice`

---

## 3. Rule B — Driver Safety Override (AC #5, #10)

### TC-3.1 — English safety keyword short-circuits

**Given** `raw_content = "Driver was injured, ambulance called to NH-48"`
**When** `AgentRunner.run_triage(event, ...)` is invoked
**Then**
- Result is `TriageResult(status="escalated_to_human_safety", classification=None, impact=None, escalation_priority="safety")`
- `classifier_agent.run_async` is NEVER called (patched with `AssertionError` side effect)
- `impact_agent.run_async` is NEVER called
- Audit log contains `runner.safety_override` event with the matched keywords

**File**: `tests/integration/test_coordinator_safety_override.py::test_english_safety_override`

### TC-3.2 — Hindi safety keyword short-circuits

**Given** `raw_content = "Ghayal ho gaya driver, durghatna ho gayi"`
**When** `AgentRunner.run_triage(event, ...)` is invoked
**Then** same as TC-3.1 with matched keywords `["ghayal", "durghatna"]`

**File**: `tests/integration/test_coordinator_safety_override.py::test_hindi_safety_override`

### TC-3.3 — Hinglish safety keyword short-circuits

**Given** `raw_content = "Accident ho gaya NH-48 pe, driver safe nahi hai"`
**When** `AgentRunner.run_triage(event, ...)` is invoked
**Then** same as TC-3.1 with matched keywords `["accident ho gaya", "safe nahi"]`

**File**: `tests/integration/test_coordinator_safety_override.py::test_hinglish_safety_override`

### TC-3.4 — Rule B beats Rule C AND Rule F (conflict resolution)

**Given** `raw_content = "E-way bill issue AND driver ghayal ho gaya in accident"` (safety + regulatory subtype + could be LOW)
**When** `AgentRunner.run_triage(event, ...)` is invoked
**Then**
- `status == "escalated_to_human_safety"` (Rule B wins)
- Neither sub-agent is invoked

**File**: `tests/integration/test_coordinator_rule_conflicts.py::test_rule_b_beats_rule_c_and_f`

---

## 4. Rule C — Regulatory Auto-Escalate (AC #6)

### TC-4.1 — LOW severity + regulatory → Impact STILL called

**Given** a Classifier that returns `ClassificationResult(severity="LOW", subtype="eway_bill_issue", type="regulatory_compliance", confidence=0.88)` and a fake Impact stub
**When** `AgentRunner.run_triage(event, ...)` is invoked
**Then**
- `result.classification.severity == "LOW"`
- `result.classification.subtype == "eway_bill_issue"`
- `result.impact is not None` (Rule C forced delegation despite LOW)
- `fake_impact_stub.call_count == 1`

**File**: `tests/integration/test_coordinator_rule_conflicts.py::test_rule_c_overrides_rule_f`

### TC-4.2 — LOW severity + non-regulatory → Rule F skips Impact

**Given** a Classifier that returns `ClassificationResult(severity="LOW", subtype="wrong_delivery", type="customer_escalation")`
**When** `AgentRunner.run_triage(event, ...)` is invoked
**Then**
- `result.status == "complete"`
- `result.impact is None`
- `impact_agent.run_async` was NOT called

**File**: `tests/integration/test_coordinator_rule_conflicts.py::test_rule_f_low_skip`

### TC-4.3 — gst_noncompliance subtype also triggers Rule C

**Given** `subtype="gst_noncompliance"`, `severity="LOW"`
**When** run
**Then** Impact IS called (Rule C list includes `gst_noncompliance`)

**File**: `tests/integration/test_coordinator_rule_conflicts.py::test_rule_c_gst_noncompliance`

### TC-4.4 — customs_hold subtype also triggers Rule C

**Given** `subtype="customs_hold"`, `severity="LOW"`
**When** run
**Then** Impact IS called

**File**: `tests/integration/test_coordinator_rule_conflicts.py::test_rule_c_customs_hold`

---

## 5. Rule D — Festival/Monsoon Context (AC #7)

### TC-5.1 — Active Diwali festival injected into runtime_context

**Given** `current_timestamp=2026-10-20T10:00:00+05:30`, `festival_context.get_festival_context` returns `{"active_festivals": [{"name": "Diwali"}]}`, `monsoon_status.get_monsoon_status` returns `{"is_active": false}`
**When** `inject_dynamic_context` runs
**Then** the mutated `system_instruction` contains `"active_festival: Diwali"` inside a `<runtime_context>` block

**File**: `tests/unit/middleware/test_context_injection.py::test_rule_d_festival_injected`

### TC-5.2 — Active monsoon for company region injected

**Given** `company.regions = ["maharashtra_west"]`, `monsoon_status.get_monsoon_status("maharashtra_west")` returns `{"is_active": true, "intensity": "heavy"}`
**When** the callback runs
**Then** the `<runtime_context>` block contains `"active_monsoon_regions: maharashtra_west"`

**File**: `tests/unit/middleware/test_context_injection.py::test_rule_d_monsoon_injected`

### TC-5.3 — Neither active → runtime_context has `none`

**Given** no festival + no monsoon
**When** the callback runs
**Then** `<runtime_context>` contains `active_festival: none` and `active_monsoon_regions: none`

**File**: `tests/unit/middleware/test_context_injection.py::test_rule_d_nothing_active`

---

## 6. Rule E — D2C Reputation Risk (AC #8)

### TC-6.1 — reputation_risk_shipments non-empty → escalation elevated

**Given** Impact returns `ImpactResult(reputation_risk_shipments=[{"shipment_id": "SHP-2024-4821", "source": "metadata_flag", "customer": "BlushBox Beauty"}])`
**When** the Coordinator finalizes the `triage_result`
**Then**
- `result.escalation_priority == "reputation_risk"`
- `"BlushBox" in result.summary`

**File**: `tests/unit/agents/test_coordinator.py::test_rule_e_reputation_elevated`

### TC-6.2 — reputation_risk_shipments empty → escalation standard

**Given** Impact returns `ImpactResult(reputation_risk_shipments=[])`
**When** finalization runs
**Then** `result.escalation_priority == "standard"`

**File**: `tests/unit/agents/test_coordinator.py::test_rule_e_no_reputation_standard`

---

## 7. Rule F — LOW Severity Skip Impact (AC #9)

### TC-7.1 — LOW + no customer-facing + non-regulatory → Impact skipped

**Given** Classifier returns `severity="LOW"`, `type="customer_escalation"`, `subtype="wrong_delivery"`, no customer-facing shipments
**When** `AgentRunner.run_triage(event, ...)` is invoked with `impact_agent.run_async` patched to raise `AssertionError`
**Then**
- `result.status == "complete"`
- `result.impact is None`
- Assertion does NOT trigger (Impact was skipped)

**File**: `tests/integration/test_coordinator_rule_conflicts.py::test_rule_f_low_skip`

### TC-7.2 — LOW + customer-facing shipments → Impact still called

**Given** Classifier returns LOW but `affected_shipments` contains a D2C customer
**When** run
**Then** Impact IS called (conservative — LOW skip only when zero customer-facing)

**File**: `tests/integration/test_coordinator_rule_conflicts.py::test_rule_f_low_but_customer_facing_keeps_impact`

---

## 8. Conflict Resolution (AC #10)

### TC-8.1 — B > C (safety + regulatory → safety wins)

**Given** safety keywords AND `subtype="eway_bill_issue"`
**When** run
**Then** `status="escalated_to_human_safety"`, sub-agents NOT called

**File**: `tests/integration/test_coordinator_rule_conflicts.py::test_rule_b_beats_c`

### TC-8.2 — C > F (regulatory LOW → Impact called)

Covered by TC-4.1.

### TC-8.3 — B > F (safety + LOW → safety wins)

**Given** safety keywords AND LOW severity non-regulatory
**When** run
**Then** safety escalation, no delegation

**File**: `tests/integration/test_coordinator_rule_conflicts.py::test_rule_b_beats_f`

### TC-8.4 — Rules A + D additive (both hints present)

**Given** voice channel AND active Diwali festival
**When** the callback runs
**Then** `<runtime_context>` contains BOTH `voice_urgency_hint` and `active_festival: Diwali`

**File**: `tests/integration/test_coordinator_rule_conflicts.py::test_rule_a_and_d_additive`

---

## 9. Context Injection Middleware (AC #3, #15)

### TC-9.1 — Happy path mutates system_instruction with 5 blocks

**Given** seeded stub with user_priya_001 context, `session.state={"user_id", "company_id", "event", "correlation_id"}`
**When** `inject_dynamic_context(cb_ctx, llm_request)` runs
**Then**
- `llm_request.config.system_instruction.parts[0].text` ENDS WITH the dynamic suffix
- The suffix contains all 5 XML blocks: `<user_context>`, `<company_context>`, `<recent_history>`, `<learned_behaviors>`, `<runtime_context>`
- The user block contains `"Name: Priya"`
- The company block contains `"NimbleFreight"`
- `audit_event("coordinator.context_injected", blocks=[5 items], ...)` was called
- Return value is `None`

**File**: `tests/unit/middleware/test_context_injection.py::test_instruction_mutated_with_context_blocks`

### TC-9.2 — Missing user_id skips injection

**Given** `session.state = {"company_id": "comp_nimblefreight"}` (no user_id)
**When** callback runs
**Then**
- `system_instruction` is unchanged (no mutation)
- `audit_event("coordinator.context_injection_skipped", reason="missing_user_or_company")` emitted
- Return is `None`

**File**: `tests/unit/middleware/test_context_injection.py::test_missing_user_id_skips`

### TC-9.3 — Missing company_id skips injection

Same as TC-9.2 but missing `company_id`.

**File**: `tests/unit/middleware/test_context_injection.py::test_missing_company_id_skips`

### TC-9.4 — SDK failure falls back gracefully

**Given** the memory provider raises `RuntimeError` on `get_user_context`
**When** callback runs
**Then**
- No exception propagates out
- `audit_event("coordinator.context_injection_failed", ...)` emitted
- `system_instruction` is unchanged
- Return is `None`

**File**: `tests/unit/middleware/test_context_injection.py::test_memory_provider_failure_graceful`

### TC-9.5 — Partial context (only user, no company profile) still injects

**Given** stub returns user_context but empty `{}` for company_context
**When** callback runs
**Then** the user block is populated, the company block is empty but present, no crash

**File**: `tests/unit/middleware/test_context_injection.py::test_partial_context_injects`

### TC-9.6 — PII bounded to user's own history

**Given** stub seeded with `user_priya_001` history AND `user_rahul_002` history under same company
**When** callback runs for `user_priya_001`
**Then** the injected `<recent_history>` block contains ONLY Priya's events, not Rahul's

**File**: `tests/unit/middleware/test_context_injection.py::test_pii_bound_to_user_scope`

### TC-9.7 — Adversarial sanitization (50-string fuzz)

**Given** a list of 50 adversarial strings loaded from `tests/fixtures/adversarial_context_strings.json`, each containing known injection patterns (`</user_context>`, `<system>ignore</system>`, `<!--injected-->`, etc.)
**When** each string is passed through `sanitize_context_field`
**Then** NONE of the output strings contain ANY of the injection patterns. All are length-capped at 2048 chars.

**File**: `tests/unit/middleware/test_context_injection.py::test_adversarial_sanitization`

**Fixture contents**: 10 `</user_context>` variants × 5 case variants + 10 `<system>` variants + 10 `<!--` comment variants + 10 unicode/control-character variants + 10 oversized strings (> 2048 chars).

### TC-9.8 — Length cap at 2048

**Given** a field containing 5000 chars of "A"
**When** sanitized
**Then** output length ≤ 2048 AND ends with `[...truncated]`

**File**: `tests/unit/middleware/test_context_injection.py::test_length_cap`

### TC-9.9 — Control char stripping

**Given** a field containing `"abc\x00def\x01ghi"`
**When** sanitized
**Then** output is `"abcdefghi"` (control chars except `\n` and `\t` removed)

**File**: `tests/unit/middleware/test_context_injection.py::test_control_char_strip`

### TC-9.10 — Festival + Monsoon tools called

**Given** the happy path fixture
**When** callback runs
**Then** both `get_festival_context` and `get_monsoon_status` were awaited exactly once

**File**: `tests/unit/middleware/test_context_injection.py::test_festival_monsoon_tools_called`

---

## 10. MemoryProvider Full Interface (AC #13)

### TC-10.1 — ABC enforces 6 abstract methods

**Given** the `MemoryProvider` ABC
**When** we try to instantiate it directly (`MemoryProvider()`)
**Then** `TypeError` is raised with a message naming ALL 6 abstract methods

**File**: `tests/unit/memory/test_provider_full_interface.py::test_abc_cannot_instantiate`

### TC-10.2 — Subclass missing a method fails

**Given** a subclass that implements only 5 of 6 methods
**When** we instantiate it
**Then** `TypeError` naming the missing method

**File**: `tests/unit/memory/test_provider_full_interface.py::test_incomplete_subclass_fails`

### TC-10.3 — Stub implements all 6

**Given** `InMemoryStubAdapter`
**When** we instantiate and call each method
**Then** no `NotImplementedError`, all return the expected default (empty list/dict)

**File**: `tests/unit/memory/test_provider_full_interface.py::test_stub_implements_all_six`

### TC-10.4 — `get_recent_exception_history` respects `limit`

**Given** stub seeded with 20 history entries
**When** we call `get_recent_exception_history(..., limit=5)`
**Then** exactly 5 are returned, most recent first

**File**: `tests/unit/memory/test_provider_full_interface.py::test_recent_history_limit`

### TC-10.5 — `get_learned_behaviors` respects `window_days`

**Given** stub seeded with behaviors for 7-day and 30-day windows
**When** we call with `window_days=30`
**Then** the 30-day entry is returned

**File**: `tests/unit/memory/test_provider_full_interface.py::test_learned_behaviors_window`

### TC-10.6 — Tenant bounding invariant (6th test)

**Given** stub seeded with `(user_priya, comp_nimble)` AND `(user_other, comp_other)` histories
**When** we call `get_recent_exception_history(user_id="user_priya_001", company_id="comp_othertenant")` (wrong pairing)
**Then** empty list (no cross-tenant leak)

**File**: `tests/unit/memory/test_provider_full_interface.py::test_tenant_bounding_invariant`

---

## 11. SupermemoryAdapter Complete (AC #13)

### TC-11.1 — `get_recent_exception_history` happy path

**Given** mocked `Supermemory` client returning 3 hits
**When** `await adapter.get_recent_exception_history("user_priya_001", "comp_nimblefreight")`
**Then**
- `client.search.execute` called with `namespace="sct:comp_nimblefreight:user_priya_001"` and `tags=["exception", "user:user_priya_001"]`
- Returns the 3 hits as dicts

**File**: `tests/unit/memory/test_supermemory_adapter_complete.py::test_get_recent_history_happy`

### TC-11.2 — `get_learned_behaviors` happy path

Similar to TC-11.1 with `tags=["learned_behavior", "window:30d"]`.

**File**: `tests/unit/memory/test_supermemory_adapter_complete.py::test_get_learned_behaviors_happy`

### TC-11.3 — SDK failure returns empty + audit log

**Given** `client.search.execute` raises `ConnectionError`
**When** `await adapter.get_recent_exception_history(...)`
**Then**
- Returns `[]`
- `audit_event("memory.search_failed", ...)` called
- No exception propagates

**File**: `tests/unit/memory/test_supermemory_adapter_complete.py::test_sdk_failure_graceful`

### TC-11.4 — Empty user_id or company_id raises ValueError

**Given** `adapter._namespace("", "user_id")`
**When** called
**Then** `ValueError("SupermemoryAdapter requires both company_id and user_id (tenant bounding)")`

**File**: `tests/unit/memory/test_supermemory_adapter_complete.py::test_namespace_rejects_empty`

### TC-11.5 — `build_with_fallback` no API key → stub

**Given** `get_secret_or_none("SUPERMEMORY_API_KEY")` returns `None`
**When** `SupermemoryAdapter.build_with_fallback()`
**Then** returns an `InMemoryStubAdapter` instance, not a `SupermemoryAdapter`

**File**: `tests/unit/memory/test_supermemory_adapter_complete.py::test_build_with_fallback_no_key`

### TC-11.6 — `build_with_fallback` SDK import error → stub

**Given** patching `supermemory` module import to raise `ImportError`
**When** `build_with_fallback()`
**Then** returns stub + `audit_event("memory.fallback_to_stub", reason="sdk_not_installed")`

**File**: `tests/unit/memory/test_supermemory_adapter_complete.py::test_build_with_fallback_sdk_missing`

---

## 12. AgentRunner (AC #14)

### TC-12.1 — run_triage seeds all 5 state keys

**Given** a valid event + user_id + company_id
**When** `AgentRunner.run_triage(event, ...)` is invoked
**Then** the session is created with `state` containing exactly `{user_id, company_id, event, current_timestamp, correlation_id}` (5 keys)

**File**: `tests/unit/runners/test_agent_runner.py::test_session_seeded_with_five_state_keys`

### TC-12.2 — Upstream safety check short-circuits without creating session

**Given** safety keyword in raw_content
**When** `run_triage` is invoked
**Then**
- `session_service.create_session` is NEVER called
- Returns `TriageResult(status="escalated_to_human_safety")`
- `audit_event("runner.safety_override", ...)` emitted

**File**: `tests/unit/runners/test_agent_runner.py::test_upstream_safety_short_circuits_no_session`

### TC-12.3 — Session is deleted in `try/finally` even on exception

**Given** `runner._runner.run_async` raises `RuntimeError`
**When** `run_triage` is invoked
**Then**
- `session_service.delete_session` is called
- `result.status == "partial"`
- `result.errors` contains `"coordinator_exception: RuntimeError"`

**File**: `tests/unit/runners/test_agent_runner.py::test_session_closed_on_exception`

### TC-12.4 — Timeout produces partial result

**Given** `run_async` takes longer than `_INVOCATION_TIMEOUT_SEC`
**When** `run_triage` is invoked
**Then** `result.status == "partial"`, `"coordinator_timeout" in result.errors`

**File**: `tests/unit/runners/test_agent_runner.py::test_timeout_partial_result`

### TC-12.5 — `processing_time_ms` populated

**Given** any successful run
**When** `run_triage` returns
**Then** `result.processing_time_ms > 0`

**File**: `tests/unit/runners/test_agent_runner.py::test_processing_time_populated`

### TC-12.6 — `coordinator_trace` non-empty

**Given** the runner yields ≥ 1 event
**When** `run_triage` returns
**Then** `len(result.coordinator_trace) >= 1`, each entry has `author`, `type`, `content_snippet`

**File**: `tests/unit/runners/test_agent_runner.py::test_trace_non_empty`

### TC-12.7 — Two invocations create isolated sessions

**Given** two calls to `run_triage` with different events
**When** both complete
**Then** each used a distinct `session_id`; state of one does NOT leak into the other

**File**: `tests/unit/runners/test_agent_runner.py::test_invocation_isolation`

### TC-12.8 — `triage_result` missing from state → partial fallback

**Given** the Coordinator completes but never writes `triage_result` to state
**When** `run_triage` returns
**Then** `result.status == "partial"`, `result.errors == ["no_triage_result_in_session_state"]`

**File**: `tests/unit/runners/test_agent_runner.py::test_missing_triage_result_partial`

### TC-12.9 — Upstream safety check is awaited (C1 regression)

**Given** `supply_chain_triage.runners.agent_runner.check_safety_keywords` is patched with an `AsyncMock` returning `{"detected": True, "keywords": ["ghayal"]}`
**When** `run_triage` is invoked with any event
**Then**
- `fake_safety.await_count == 1` (proves the coroutine was awaited, not left dangling)
- `fake_safety.call_count == 1`
- `result.status == "escalated_to_human_safety"`

**Rationale**: The Sprint 1 `check_safety_keywords` tool is an `async def`. Calling it without `await` returns a coroutine object whose `.get("detected")` raises `AttributeError`. This test pins the contract so a future refactor cannot silently drop the `await`.

**File**: `tests/unit/agents/test_coordinator.py::test_upstream_safety_check_is_awaited`

---

## 13. Full Pipeline Integration (AC #1, #11)

### TC-13.1 — NH-48 end-to-end (the headline)

**Given**
- Firestore emulator seeded with `comp_nimblefreight` + NH-48 shipments (Sprint 2 seed)
- `InMemoryStubAdapter` seeded with Priya's full context (user, company, recent history, learned behaviors)
- Real `classifier_agent` + `impact_agent`
- `ExceptionEvent` with NH48_RAW Hinglish raw_content and `source_channel="whatsapp_voice"`

**When** `AgentRunner.run_triage(event, user_id="user_priya_001", company_id="comp_nimblefreight")`

**Then** (every field must match — see PRD §12-J golden trace):
- `result.status == "complete"`
- `result.classification.type == "carrier_capacity_failure"`
- `result.classification.subtype == "vehicle_breakdown_in_transit"`
- `result.classification.severity == "CRITICAL"`
- `result.classification.confidence >= 0.85`
- `result.impact is not None`
- `result.impact.critical_path_shipment_id == "SHP-2024-4821"`
- `result.impact.recommended_priority_order == ["SHP-2024-4821", "SHP-2024-4823", "SHP-2024-4824", "SHP-2024-4822"]`
- `len(result.impact.affected_shipments) == 4`
- `result.escalation_priority == "reputation_risk"`
- `"BlushBox" in result.summary OR "campaign" in result.summary.lower()`
- `80 <= len(result.summary) <= 400`
- `len(result.coordinator_trace) >= 2`
- `0 < result.processing_time_ms < 30000`

**File**: `tests/integration/test_coordinator_full_pipeline.py::test_nh48_end_to_end`

### TC-13.2 — Cross-tenant isolation (AC #16)

**Given** NH-48 event, seeded stub (Priya's context), Firestore seed
**When** `run_triage(event, user_id="user_other_001", company_id="comp_othertenant")`
**Then**
- Result does NOT contain `"SHP-2024-4821"` in any string
- Result does NOT contain `"BlushBox"` in summary
- Result does NOT contain `"NimbleFreight"` in summary
- If `result.impact` is non-null, no shipment has `customer == "BlushBox Beauty"`
- No `comp_nimblefreight` context was injected into the system instruction

**File**: `tests/integration/test_coordinator_full_pipeline.py::test_cross_tenant_isolation`

### TC-13.3 — Sub-agent failure → partial status

**Given** a monkey-patched `classifier_agent.run_async` that raises `GuardrailsValidationError`
**When** `run_triage` is invoked on NH-48
**Then**
- `result.status == "partial"`
- `result.errors` contains `"coordinator_exception: GuardrailsValidationError"` or similar
- `result.classification is None`
- `impact_agent.run_async` was NOT called
- `audit_event("runner.exception", ...)` emitted

**File**: `tests/integration/test_coordinator_full_pipeline.py::test_sub_agent_failure_partial`

### TC-13.4 — Missing user_id → generic summary

**Given** NH-48 event, `user_id=""`, `company_id=""`
**When** `run_triage` is invoked
**Then**
- `result.status` ∈ `{"complete", "partial"}`
- `result.summary` is non-empty
- `"Priya" not in result.summary` (no personalization)
- `audit_event("coordinator.context_injection_skipped", reason="missing_user_or_company")` emitted

**File**: `tests/integration/test_coordinator_full_pipeline.py::test_missing_user_generic_summary`

---

## 14. ADK AgentEvaluator (AC #12)

### TC-14.1 — All 10 eval cases pass

**Given** `tests/evals/coordinator_eval.json` (10 cases per PRD §12-H), `tests/evals/test_config.json` with thresholds `tool_trajectory_avg_score=0.9`, `response_match_score=0.8`, `num_runs=3`
**When** `await AgentEvaluator.evaluate(agent_module="supply_chain_triage.agents.coordinator", eval_dataset_file_path_or_dir="tests/evals/coordinator_eval.json")`
**Then** no exceptions — all 10 cases pass both thresholds across 3 runs

**File**: `tests/integration/test_coordinator_adk_eval.py::test_coordinator_eval_passes`

### Per-case expected `tool_uses` summary (for fast triage if a case fails):

| Case | Expected `tool_uses` |
|------|-----------------------|
| 01 NH-48 full pipeline | `[transfer→Classifier, transfer→Impact]` |
| 02 Safety Hinglish | `[]` (no transfers) |
| 03 Regulatory LOW → Rule C | `[transfer→Classifier, transfer→Impact]` |
| 04 LOW skip → Rule F | `[transfer→Classifier]` only |
| 05 WhatsApp voice → Rule A | `[transfer→Classifier, transfer→Impact]` |
| 06 Festival context → Rule D | `[transfer→Classifier, transfer→Impact]` |
| 07 D2C reputation → Rule E | `[transfer→Classifier, transfer→Impact]` |
| 08 B2B standard | `[transfer→Classifier, transfer→Impact]` |
| 09 Missing user | `[transfer→Classifier, transfer→Impact]` |
| 10 Sub-agent failure | `[transfer→Classifier]` only (Impact never reached) |

---

## 15. Test Fixtures (reusable across files)

### Fixture registry — `tests/conftest.py` additions for Sprint 3

| Fixture | Scope | Returns | Purpose |
|---------|-------|---------|---------|
| `fake_classifier_low_regulatory` | function | Mock `classifier_agent` returning `ClassificationResult(severity=LOW, subtype=eway_bill_issue, ...)` | TC-4.1 |
| `fake_classifier_low_nonreg` | function | Mock returning `(LOW, wrong_delivery)` | TC-4.2, TC-7.1 |
| `fake_impact_stub` | function | Mock `impact_agent` returning a plain `ImpactResult` with empty reputation list | TC-4.1 |
| `fake_impact_with_reputation` | function | Mock returning `ImpactResult(reputation_risk_shipments=[{customer: BlushBox, ...}])` | TC-6.1 |
| `seeded_stub_provider` | function | `InMemoryStubAdapter` with full Priya context | TC-13.1, TC-13.2 |
| `firestore_emulator_with_nh48_seed` | session | Firestore emulator + Sprint 2 seed script executed | TC-13.* |
| `patched_festival_diwali` | function | Monkey-patches `get_festival_context` to return Diwali active | TC-5.1 |
| `patched_monsoon_active` | function | Monkey-patches `get_monsoon_status` to return active | TC-5.2 |
| `adversarial_context_strings` | session | Loads `tests/fixtures/adversarial_context_strings.json` (50 strings) | TC-9.7 |

---

## 16. Coverage Targets (AC #17)

Per-module coverage targets for `pytest --cov --cov-fail-under=85`:

| Module | Target | Tests |
|--------|--------|-------|
| `supply_chain_triage.agents.coordinator` | 100% | TC-1.1, TC-1.2, TC-1.3 + rule tests |
| `supply_chain_triage.middleware.context_injection` | 100% | TC-9.1 through TC-9.10 |
| `supply_chain_triage.memory.provider` | 100% | TC-10.* |
| `supply_chain_triage.memory.supermemory_adapter` | 90% | TC-11.* (Sprint 2 may already cover old methods) |
| `supply_chain_triage.memory.stub_adapter` | 100% | TC-10.3 |
| `supply_chain_triage.runners.agent_runner` | 95% | TC-12.* |

---

## 17. Execution Order

Run tests in this order during Sprint 3 (fast feedback first):

```bash
# Day 1 — incremental as modules land
pytest tests/unit/agents/test_coordinator.py::test_coordinator_instantiates -v
pytest tests/unit/memory/test_provider_full_interface.py -v
pytest tests/unit/memory/test_supermemory_adapter_complete.py -v
pytest tests/unit/middleware/test_context_injection.py -v
pytest tests/unit/runners/test_agent_runner.py -v

# Day 2 — delegation rules + integration
pytest tests/unit/agents/test_coordinator.py -v
pytest tests/integration/test_coordinator_safety_override.py -v
pytest tests/integration/test_coordinator_rule_conflicts.py -v
pytest tests/integration/test_coordinator_full_pipeline.py -v

# Day 2 Hour 5–6 — ADK eval (slowest)
pytest tests/integration/test_coordinator_adk_eval.py -v

# Day 2 Hour 8 — coverage + pre-commit
pytest --cov=src/supply_chain_triage --cov-report=term-missing --cov-fail-under=85
pre-commit run --all-files
```

---

## 18. Cross-References

- PRD: `./prd.md` — full specification
- Risks: `./risks.md` — pre-mortem assessment
- Spec: [[Supply-Chain-Agent-Spec-Coordinator]] — authoritative rules
- Demo scenario: [[Supply-Chain-Demo-Scenario-Tier1]] — NH-48 anchor

---

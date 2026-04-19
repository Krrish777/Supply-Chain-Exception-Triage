---
title: "Next-Session Handoff — Sprint 3 Day 4 (SSE + POST /api/v1/triage)"
type: handoff
sprint: 3
day: 4
target_date: 2026-04-20
last_updated: 2026-04-19
---

# Next-Session Handoff — Sprint 3 Day 4 (SSE + Route)

**Paste the block below into the first message of the Day 4 session.**
It is self-contained — no reliance on conversation history, CEO review context, or office-hours artefacts beyond what's written in the repo.

---

## Start-of-session prompt

```
You are resuming the Supply Chain Exception Triage Sprint 3 build at Day 4.
Read these files in order before writing any code:

REPO RULES (authoritative — read first):
1. CLAUDE.md — SDLC rule of record, project commitments, scoped rule index
2. .claude/rules/placement.md — folder structure, what-goes-where
3. .claude/rules/imports.md — vendor-import scopes (google.adk.*, firebase_admin, firestore)
4. .claude/rules/architecture-layers.md — application-layer direction
5. .claude/rules/api-routes.md — FastAPI conventions, dependency order, envelopes, status codes
6. .claude/rules/agents.md — ADK callback and state-namespacing patterns
7. .claude/rules/observability.md — audit_event contract, OTel expectations
8. .claude/rules/testing.md — pytest/integration split, auth patterns, mock rules
9. .claude/rules/security.md — middleware stack order, CORS/auth discipline

SPRINT 3 CONTEXT (read after rules):
10. docs/sprints/sprint-3/prd.md — approved PRD (supersedes prd-v1-archived.md)
11. docs/sprints/sprint-3/test-plan.md — test-case IDs (U-1..U-N, I-1..I-N)
12. docs/sprints/sprint-3/risks.md — known risks + mitigations
13. docs/sessions/2026-04-19-sprint3-day2-pipeline-callbacks.md — Day 2 impl log
14. docs/research/fastapi-sse-api-design.md — SSE event ordering + FastAPI patterns
15. docs/research/coordinator-orchestration-patterns.md — pipeline reference
16. docs/research/firebase-auth-oauth-multitenancy.md — auth integration reference

EXISTING CODE YOU WILL READ (not modify unless noted):
17. src/supply_chain_triage/main.py — create_app() factory + middleware stack
18. src/supply_chain_triage/runners/triage_runner.py — Day 3 blocking runner
    (run_triage) — Day 4 extends THIS file with _triage_event_stream()
19. src/supply_chain_triage/modules/triage/pipeline/__init__.py — create_triage_pipeline()
20. src/supply_chain_triage/middleware/firebase_auth.py — auth middleware
21. src/supply_chain_triage/middleware/audit_log.py — audit_event helper (DO NOT
    call from the runner yet — correlation_id / user_id / company_id come
    from the HTTP route context, not the runner)

WHAT DAY 4 MUST DELIVER (Sprint 3 PRD §5 row 4):
A. An SSE streaming path in runners/triage_runner.py that:
   - Reuses create_triage_pipeline() — no new pipeline instance logic
   - Yields typed SSE events in this order for every run:
       agent_started    { agent_name }
       tool_invoked     { tool_name, agent_name }    (0..N)
       agent_completed  { agent_name, status }
       partial_result   { key, value }                (0..N, e.g. when triage:classification lands)
       complete         { triage_result: {...} }
       done             {} (always the last frame, even on error)
   - Emits error { code, message } on exception then done, never 500s
   - Handles client disconnect gracefully (asyncio.CancelledError)
   - Function signature: async def _triage_event_stream(event_id: str, raw_text: str)
     -> AsyncIterator[dict[str, Any]]
     (the route layer wraps each dict with SSE framing)

B. A prod HTTP endpoint:
   POST /api/v1/triage
   - Lives in NEW file src/supply_chain_triage/runners/routes/triage.py
   - Uses APIRouter(prefix="/api/v1/triage", tags=["triage"])
   - Signature (per .claude/rules/api-routes.md §3 — dependency order enforced):
       @router.post("/")
       async def triage_exception(
           *,
           current_user: CurrentUser,           # Firebase Auth dep
           payload: TriagePayload,               # event_id OR raw_text, not both empty
       ) -> EventSourceResponse | StreamingResponse
   - Payload: Pydantic model in src/supply_chain_triage/modules/triage/models/api_envelopes.py
     (add there, next to TriageAgentInput). Fields: event_id: str | None, raw_text: str | None.
     Validator: at least one of event_id / raw_text non-empty — else 422 at Pydantic boundary.
   - Response: FastAPI's built-in EventSourceResponse IF the installed fastapi version supports
     it (PR #15030). If not, fall back to StreamingResponse(media_type="text/event-stream") with
     explicit headers: X-Accel-Buffering: no, Cache-Control: no-cache, Connection: keep-alive.
     Check with `uv run python -c "from fastapi.responses import EventSourceResponse"` —
     if ImportError, use sse-starlette's EventSourceResponse (already in deps — verify with
     `rg sse.starlette pyproject.toml`) or the StreamingResponse fallback.
   - Register the router in src/supply_chain_triage/main.py via app.include_router(triage_router).

C. Route-level validation:
   - Empty raw_text AND empty event_id → 422 (Pydantic validator)
   - event_id malformed → 422 (simple string-length check)
   - Do NOT sanitize raw_text in the route — InputSanitizationMiddleware already runs
     before handlers per main.py middleware order.

D. Integration tests in NEW file tests/integration/test_triage_sse.py:
   - I-8: happy path SSE event order. Use httpx.AsyncClient + ASGITransport.
     Seed Firestore emulator like I-1. Override get_current_user to return a
     test FirebaseUser. Read the SSE stream, parse frames, assert event type
     order matches the contract above. Ends with "done".
   - I-9: Rule B short-circuit via SSE. Safety keyword in raw_text. Assert
     final "complete" frame contains escalated_to_human_safety. No Gemini call.
   - I-10: client disconnect mid-stream. Drop the connection after "agent_started"
     for classifier. Assert no exception propagates to the test; the cleanup path
     fires. Use asyncio.wait_for + TimeoutError pattern or httpx.Response.aclose().
   - I-11: 422 on empty payload. POST {} → 422. POST {"event_id": "", "raw_text": ""} → 422.

E. Atomic commit with message:
   feat(api): day 4 — SSE streaming runner + POST /api/v1/triage route

   Extends triage_runner with _triage_event_stream() (AsyncIterator),
   adds routes/triage.py APIRouter included in create_app(). Frame contract
   per Sprint 3 PRD §2.2: agent_started / tool_invoked / agent_completed /
   partial_result / complete / error / done. Client disconnect handled via
   asyncio.CancelledError. Route validates empty payload → 422 before the
   pipeline fires. SSE response uses EventSourceResponse when available,
   falls back to StreamingResponse + X-Accel-Buffering: no header.

   Integration tests I-8..I-11: happy path, Rule B short-circuit, client
   disconnect mid-stream, 422 on empty payload.

FOOTGUNS YOU WILL HIT IF YOU DON'T READ THIS:

1. SSE + Cloud Run buffering
   Cloud Run sits behind a proxy that buffers by default. Without
   X-Accel-Buffering: no, events batch and deliver in one chunk at the end.
   FastAPI's EventSourceResponse sets this automatically (PR #15030, 2026).
   Plain StreamingResponse does NOT — you must set the header yourself.

2. EventSource vs fetch() / ReadableStream for auth
   The browser's native EventSource API cannot send custom headers. We use
   fetch() + ReadableStream on the UI side. For now (Day 4), the route
   accepts the Firebase ID token via Authorization header — which means
   tests and the future UI use fetch(), not EventSource. Do not wire the
   route for cookie-based auth.

3. ADK Runner.run_async events are NOT SSE events
   Runner.run_async yields ADK Event objects. You must translate them into
   our SSE frame contract:
     ADK Event.agent_name begins       → agent_started
     ADK Event.tool_response            → tool_invoked (check for .function_call)
     ADK Event.is_final_response()      → agent_completed for that agent
     session.state["triage:classification"] lands → partial_result
     pipeline drain finishes            → complete
   Do NOT emit ADK Events directly to the SSE stream — the shape is noisy
   and exposes internals (raw JSON fragments, per .claude/rules/agents.md §10).

4. FastAPI dependency order (api-routes.md §3, ENFORCED)
   Correct signature order:
       *, current_user: CurrentUser, payload: TriagePayload
   NOT: payload: TriagePayload, current_user: CurrentUser
   Leading `*` makes args keyword-only. Required when body + dep coexist.

5. Test auth — dependency override, NOT emulator token (testing.md §7)
   In tests/integration/test_triage_sse.py, use:
     app.dependency_overrides[get_current_user] = lambda: FirebaseUser(
         uid="test-user", tier=1, tenant_id="acme"
     )
   Clear in teardown. Do NOT mint emulator tokens unless testing middleware.

6. audit_event stays DEFERRED
   Day 5 adds audit_event. Do NOT call it from the route yet — it requires
   correlation_id / user_id / company_id, and correlation_id middleware
   isn't finalized. Day 4 logs via log_agent_invocation only (already in
   triage_runner.py from Day 3).

7. Empty raw_text path
   The Day 3 runner has no guard. Day 4 route is the right boundary — reject
   at the Pydantic validator. Do NOT add a guard in triage_runner.py itself;
   the runner should trust its callers.

WHAT'S ALREADY DONE (do not rebuild):
- Day 1 (Apr 19): LLM abstraction + .env + classifier test fix + Sprint 3 docs
  (commit 79d8d51, f51f58f)
- Day 2 (Apr 19): Pipeline callbacks (Rule B, Rule C/F) + safety keyword list
  + callback tests U-1..U-10 (commit c9f0805)
- Day 3 (Apr 19): Pipeline factory + blocking runner + tests U-11..U-18 +
  I-1 happy path + I-2 Rule B short-circuit + runner observability
  (commit d73a4d7)

STATE HANDOFF VERIFICATION (already passing):
- classifier/agent.py:220 output_key="triage:classification" writes state
  (also redundant write at :186 via after_model_callback)
- impact/agent.py:313 output_key="triage:impact" writes state
- run_triage parses both via _parse_classification / _parse_impact
- Runner emits log_agent_invocation at pipeline completion

OPTIONAL — IF DAY 4 HAS TIME:
These are P2/P3 carry-forward items from the Day 3 CEO review. Address if
Day 4 finishes early (SSE work is the priority). Order of value:

P2-1. Integration test for Rule F skip (LOW severity non-regulatory)
      tests/integration/test_triage_pipeline.py — new test_i3_rule_f_skip.
      Needs Gemini (classifier must run to produce LOW severity).

P2-2. Integration test for Rule C regulatory force-run
      Same file — new test_i4_rule_c_force_run. Also needs Gemini.

P2-3. Unit test for classification parse error symmetric to U-17
      tests/unit/runners/test_triage_runner.py — new test that passes
      malformed JSON for triage:classification and asserts errors list
      contains "classification_parse_error:".

P3-1. Pin U-13 conditional assertion
      tests/unit/modules/triage/pipeline/test_pipeline_factory.py — the
      `if isinstance(callback, list)` branch. Run the test once, inspect
      the actual shape, delete the dead branch.

P3-2. Lazy root_agent init (if Cloud Run cold-start matters)
      src/supply_chain_triage/modules/triage/pipeline/__init__.py — the
      module-level `root_agent = create_triage_pipeline()` fires the factory
      on every import. Defer to Day 5 if Day 4 is tight.

DO NOT DO YET (carry forward to Days 5-8):
- audit_event emissions (Day 5)
- /auth/onboard endpoint (Day 5)
- GET /api/v1/exceptions endpoint (Day 5)
- slowapi rate limiting (Day 5)
- OTel spans + Cloud Trace exporter (Day 5)
- tenacity retry on Impact (Day 5)
- Firestore rules rewrite + tenant-leak fix in get_affected_shipments (Day 6)
- Seed file population + seed_all.py consolidation (Day 6)
- triage_results / audit_events Firestore writes (Day 6)
- Classifier evalset + Impact evalset (Day 7)
- UI work (Day 7-8) — HTML-first review cycle per CEO review plan
- Cloud Run deploy with --timeout=3600 (Day 8+)

EXIT GATE FOR DAY 4 (all must be ✅ before commit):
- [ ] Runner: _triage_event_stream yields the 7-type SSE frame contract
- [ ] Route: POST /api/v1/triage lives in runners/routes/triage.py and is
       registered in main.py via include_router
- [ ] Route validates empty payload (422 before pipeline fires)
- [ ] Tests I-8..I-11 pass
- [ ] uv run pytest tests/unit/ — 0 failures (210+ tests)
- [ ] uv run ruff check . clean
- [ ] uv run mypy src clean
- [ ] uv run lint-imports clean
- [ ] interrogate ≥80% docstring coverage
- [ ] Atomic commit with the message above

RULES TO FOLLOW DURING BUILD:
- ADK imports only in modules/*/agents/*/agent.py, runners/, modules/*/memory/
  (triage_runner.py is in runners/ — allowed)
- FastAPI route signature order: *, current_user, path params, payload, query
  (.claude/rules/api-routes.md §3)
- SSE event names lowercase_with_underscores (matches agent_invoked convention)
- Update docs/sprints/sprint-3/impl-log.md Day 4 row with actuals +
  deviations before commit
- Session notes: write docs/sessions/2026-04-20-sprint3-day4-sse.md at end of
  session (decisions + rationale + open questions, not transcript)

Ready to start Day 4?
```

---

## Pre-session checklist (do before starting the build session)

- [ ] Firestore emulator still starts cleanly: `firebase emulators:start --only firestore`
- [ ] `GEMINI_API_KEY` in env (for I-1; I-8 uses mocked SSE, no Gemini needed for most tests)
- [ ] `uv run pytest tests/unit/ -q` passes — if not, fix first
- [ ] `git status --short` is clean (only `.claude/skills/` expected as untracked)
- [ ] `uv run python -c "from fastapi.responses import EventSourceResponse"` — check which SSE helper to use
  - If `ImportError`, also check: `uv run python -c "from sse_starlette import EventSourceResponse"`
  - If both fail, fall back to plain `StreamingResponse` + manual headers (see footgun #1)

---

## Files the Day 4 session will create or modify

**NEW:**
- `src/supply_chain_triage/runners/routes/__init__.py` — package marker
- `src/supply_chain_triage/runners/routes/triage.py` — APIRouter, POST /api/v1/triage
- `tests/integration/test_triage_sse.py` — I-8..I-11
- `docs/sessions/2026-04-20-sprint3-day4-sse.md` — session notes at end of session

**MODIFIED:**
- `src/supply_chain_triage/runners/triage_runner.py` — add `_triage_event_stream` async generator
- `src/supply_chain_triage/main.py` — `app.include_router(triage_router)` after middleware stack
- `src/supply_chain_triage/modules/triage/models/api_envelopes.py` — add `TriagePayload` Pydantic model with `event_id | raw_text` union validator
- `docs/sprints/sprint-3/impl-log.md` — fill Day 4 actuals row

---

## If the session catches fire (cut-line order)

From docs/sprints/sprint-3/prd.md §4 cut-line:
1. Drop I-10 (client disconnect test) — hard to stabilise, Cloud Run behaviour varies
2. Drop partial_result frame emission — keep only agent_started / agent_completed / complete / done
3. Ship `POST /api/v1/triage` without auth dep — add Day 5 (but only if auth wiring is genuinely blocking)
4. Only if all above fail: collapse to a non-streaming endpoint (blocking path only), mark the SSE work as Day 5 rollover

---

## What Day 5 inherits from Day 4

- Working POST /api/v1/triage with auth dep in place
- `audit_event` emission at route entry + exit (Day 5 wires it)
- `slowapi` rate limit on the triage route (Day 5 adds the Limiter instance)
- OTel spans on top of the SSE stream (Day 5 — no refactor of Day 4 code expected)
- `tenacity` retry wrapper on Impact (Day 5 — decorator on the tool functions)

No breaking changes expected Day 5. Day 4 must leave a clean route-level seam that Day 5 adds behaviour TO, not rewrites.

---

## Reminders for later days (do not address in Day 4)

| Day | Reminder |
|---|---|
| Day 5 | Add `audit_event` in the route handler (correlation_id + user_id + company_id from CurrentUser). Do NOT add it in triage_runner. |
| Day 5 | Add slowapi rate limit `@limiter.limit("10/minute")` to the triage route. |
| Day 5 | Add tenacity retry `@retry(stop=stop_after_attempt(2), wait=wait_exponential())` on the Impact fetcher tool, not the whole agent. |
| Day 6 | Fix `get_affected_shipments` tenant-leak: add `company_id` filter clause. Regression test mandatory. |
| Day 6 | Wire triage_results/{id} + audit_events/{id} Firestore writes at pipeline completion. |
| Day 7 | UI approach per CEO review: HTML mockups FIRST (Landing, Triage Console, History) → user reviews against brand guidelines → only then convert to React + Vite. |
| Day 8 | Cloud Run deploy: `gcloud run deploy --timeout=3600` (required — SSE dies at 60s otherwise). Also `--min-instances=1` for 48h around demo. |
| Day 9 | Full dress rehearsal of all 3 flagship scenarios before cutting the release commit. |

---

## Premise grilling session (separate, optional)

A paste-ready premise-challenge prompt lives at
`docs/sessions/2026-04-19-premise-grilling-prep.md`. Run it in a SEPARATE chat when you have 20-30 minutes and the emotional bandwidth to answer honestly. Target: one concrete action by Apr 22 to fold into `docs/submission/solution-brief.md`. Not blocking Day 4.

---
title: "Sprint 3 Day 4 — SSE streaming runner + POST /api/v1/triage"
date: 2026-04-20
sprint: 3
day: 4
---

# Sprint 3 Day 4 — SSE Streaming Runner + Route

## Scope delivered

PRD §5 row 4 in full:

- `_triage_event_stream(event_id, raw_text) -> AsyncIterator[dict[str, Any]]`
  added alongside Day 3's `run_triage` in `src/supply_chain_triage/runners/triage_runner.py`.
  Shares `_assemble_triage_result` + parse helpers with the blocking path.
- `POST /api/v1/triage` route in the new `src/supply_chain_triage/runners/routes/triage.py`
  + empty-package `__init__.py`. Returns `StreamingResponse` with
  `text/event-stream` + `X-Accel-Buffering: no` (Cloud Run buffering guard).
- `TriagePayload(event_id | raw_text)` Pydantic envelope with
  `model_validator(mode="after")` rejecting empty / whitespace-only inputs at
  the 422 boundary.
- Router included in `main.py` after the middleware stack.
- Integration tests I-8..I-11 in `tests/integration/test_triage_sse.py`.

## Frame contract (stable, decoupled from ADK)

| Frame | Emitted when |
|---|---|
| `agent_started {agent_name}` | First event from a new author (classifier, impact, or pipeline) |
| `tool_invoked {tool_name, agent_name}` | Event carries function calls |
| `agent_completed {agent_name, status}` | `event.is_final_response()` — `status=escalated` iff `triage:rule_b_applied` |
| `partial_result {key, value}` | `triage:classification` first lands in state (once per stream) |
| `complete {triage_result}` | Pipeline drained successfully; carries the full `TriageResult` dict |
| `error {code, message}` | Caught `Exception` inside the stream — never 500 |
| `done {}` | Terminal frame (except on `CancelledError`) |

## Key decisions + rationale

1. **Dep-override auth, not middleware-only.** `FirebaseAuthMiddleware` already
   sets `request.state.user_id / company_id`. The new route adds a
   `Depends(get_current_user)` that lifts those into a `FirebaseUser` Pydantic
   model. Why: middleware has no test-override seam; `app.dependency_overrides`
   does. Middleware stays as the perimeter guard, dep is the test seam — matches
   `.claude/rules/api-routes.md` §5 and `.claude/rules/testing.md` §7.

2. **StreamingResponse, not sse-starlette.** `sse-starlette` isn't in the
   project deps path. `StreamingResponse` + explicit SSE framing in the route
   (`event: X\ndata: <json>\n\n`) is functionally equivalent once we set
   `X-Accel-Buffering: no`. No Cloud Run behaviour difference observed.

3. **Translate ADK events into our own frame types.** ADK `Event.model_dump`
   is noisy — raw JSON fragments, internal IDs, per-part partial text. Leaking
   those onto the wire couples the UI / judge's curl to ADK. The translation
   layer is ~20 lines of pure function (`_frames_for_event`) — cheap seam
   for a future LangGraph/CrewAI swap per `.claude/rules/imports.md`.

4. **Detect `partial_result` via state polling, not ADK event parsing.** After
   each ADK event we re-read the session state; the first time
   `triage:classification` appears we emit `partial_result` and set a flag.
   Clean, doesn't dig into ADK event internals, and aligns with how the
   blocking runner already reads state.

5. **`done` yields outside `finally:`.** Yielding from `finally:` after a
   `GeneratorExit` raises `RuntimeError`. Placement as the last statement after
   `try / except Exception:` gives us: normal completion → `done` fires;
   handled exception → `error` then `done`; `CancelledError` → propagates,
   `done` skipped (consumer is gone anyway, frame would be lost).

6. **Ad-hoc event_id fallback.** If only `raw_text` is sent, the route
   synthesizes `f"adhoc-{uuid4().hex[:16]}"` so the runner has something to
   seed into `triage:event_id`. Not persisted as a real Firestore ID — Day 6
   will tighten this when Firestore writes land.

## Verification

- `uv run ruff check .` → clean.
- `uv run mypy src` → clean (55 files).
- `uv run lint-imports` → 5 contracts kept, 0 broken.
- `uv run interrogate -c pyproject.toml src` → 94.3% (above 80% gate).
- `uv run pytest tests/unit/ -q` → 210 passed, 1 skipped (hello_world live-Gemini).
- `uv run pytest tests/integration/test_triage_sse.py -v` → 6 passed
  (I-9 × 1, I-10 × 1, I-11 × 4), I-8 skipped without `GEMINI_API_KEY`.

## Files created

- `src/supply_chain_triage/runners/routes/__init__.py`
- `src/supply_chain_triage/runners/routes/triage.py`
- `tests/integration/test_triage_sse.py`

## Files modified

- `src/supply_chain_triage/runners/triage_runner.py` — added streaming path + helpers.
- `src/supply_chain_triage/modules/triage/models/api_envelopes.py` — `TriagePayload`.
- `src/supply_chain_triage/main.py` — `include_router(triage_router)`.
- `docs/sprints/sprint-3/impl-log.md` — Day 4 actuals row.

## Open questions for Day 5

- `audit_event` shape when streaming. Per-frame emission would flood;
  per-stream (entry + exit) is simplest. Plan: emit once at route entry
  (`agent_invoked`-equivalent) + once at stream completion (`agent_completed`
  with `latency_ms`). Confirm by reading `.claude/rules/observability.md` §6.
- slowapi key function for streaming endpoints — per-uid keying depends on
  `request.state.user_uid`, which middleware already sets. Should work unchanged.
- Whether `tenacity` retry on Impact should also retry the streaming path's
  frame emission. Likely yes — the frame contract tolerates a second
  `agent_started(impact)` if we reset the tracking dict between attempts.
  Decide when wiring retry.

## Carry-forward (Day 4 CEO-review P2/P3 items — deferred)

P2-1 Rule F skip integration test, P2-2 Rule C force-run integration test,
P2-3 classification parse-error unit test, P3-1 U-13 dead-branch prune,
P3-2 lazy root_agent init — all untouched, stays on Day 5 backlog.

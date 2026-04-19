---
title: FastAPI SSE + API design for Tier 1 Triage
type: research
tags: [fastapi, sse, streaming, cloud-run, adk, firebase-auth, pagination, api-design]
status: ready-for-prd
last_updated: 2026-04-18
confidence: high
audience: implementers of /api/v1/triage and /api/v1/exceptions
extends:
  - "[[zettel-fastapi-sse-cloud-run]]"   # header-trio + buffering first principles
related:
  - ".claude/rules/api-routes.md"
  - ".claude/rules/agents.md"
  - ".claude/rules/security.md"
  - ".claude/rules/observability.md"
  - ".claude/rules/firestore.md"
  - ".claude/rules/models.md"
sources:
  - https://fastapi.tiangolo.com/tutorial/server-sent-events/
  - https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse
  - https://google.github.io/adk-docs/events/
  - https://google.github.io/adk-docs/streaming/dev-guide/part3/
  - https://google.github.io/adk-docs/runtime/event-loop/
  - https://docs.cloud.google.com/run/docs/configuring/request-timeout
  - https://discuss.google.dev/t/google-adk-next-js-sse-streaming-stops-working-on-cloud-run/294138
  - https://github.com/sysid/sse-starlette
  - https://deepwiki.com/sysid/sse-starlette/3.5-client-disconnection-detection
  - https://github.com/fastapi/fastapi/discussions/14552
  - https://github.com/fastapi/fastapi/issues/3766
  - https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
  - https://html.spec.whatwg.org/multipage/server-sent-events.html
  - https://firebase.google.com/docs/auth/admin/verify-id-tokens
  - https://github.com/firebase/firebase-admin-python/blob/main/firebase_admin/_token_gen.py
  - https://github.com/firebase/firebase-admin-python/issues/624
---

# FastAPI SSE + API design for Tier 1 Triage

> **Scope.** This document fixes the HTTP contract for the Tier 1 production
> API: one SSE streaming endpoint (`POST /api/v1/triage`) and one paginated
> list endpoint (`GET /api/v1/exceptions`). Existing test routes
> (`/api/v1/classify`, `/api/v1/impact`) are kept but demoted to debug-only.
> Every design decision here respects the rules in
> `.claude/rules/{api-routes,agents,security,observability,firestore,models}.md`
> and extends the header-trio first-principles analysis in
> `docs/research/zettel-fastapi-sse-cloud-run.md`.

---

## 1. Executive summary

### 1.1 The API surface for Tier 1

Three user-facing resources, all under `/api/v1/`:

| Method | Path                      | Purpose                                                    | Response       | Auth     |
| ------ | ------------------------- | ---------------------------------------------------------- | -------------- | -------- |
| `POST` | `/api/v1/triage`          | Run the full `SequentialAgent(classifier → impact)` pipeline on one exception, stream progress as SSE | `text/event-stream` | Firebase |
| `GET`  | `/api/v1/exceptions`      | Cursor-paginated tenant-scoped list of past exceptions + their triage status | `application/json` | Firebase |
| `GET`  | `/api/v1/exceptions/{id}` | Fetch the complete `TriageResult` for one exception        | `application/json` | Firebase |

Two additional non-production endpoints, mounted only when
`settings.ENV in {"dev","staging"}`:

| Method | Path               | Purpose                                      |
| ------ | ------------------ | -------------------------------------------- |
| `POST` | `/api/v1/classify` | Classifier-only debug path (auth still on)   |
| `POST` | `/api/v1/impact`   | Impact-only debug path (auth still on)       |

Plus the standard operator routes:

| Method | Path       | Purpose                                 |
| ------ | ---------- | --------------------------------------- |
| `GET`  | `/health`  | Liveness — no auth                      |
| `GET`  | `/ready`   | Readiness — checks Firestore + Gemini   |
| `GET`  | `/version` | Build / commit SHA — no auth            |

### 1.2 The SSE event contract (headline)

`POST /api/v1/triage` emits this ordered event sequence; each bullet is one
SSE frame (`event: <name>\ndata: <json>\n\n`):

```
agent_started   {agent:"classifier"}
tool_invoked    {tool:"get_exception_event", agent:"classifier_fetcher"}
agent_completed {agent:"classifier_fetcher"}
agent_completed {agent:"classifier"}
partial_result  {classification:{…}}       <-- UI renders classifier card NOW
agent_started   {agent:"impact"}
tool_invoked    {tool:"get_classification"}
agent_completed {agent:"impact_fetcher"}
agent_completed {agent:"impact"}
complete        {triage_result:{…}}
done            [DONE]                     <-- terminator
```

On any sub-agent failure (graceful-degradation per `.claude/rules/agents.md`
§12):

```
error           {code:"IMPACT_UNAVAILABLE", message:"…", recoverable:true}
complete        {triage_result:{classification:{…}, impact:null}}
done            [DONE]
```

On unrecoverable errors we still emit `error` + `done` — **never drop the
stream open, never 500 mid-stream** (connection already switched to 200 SSE).

### 1.3 The auth model

Every non-`/health` request carries `Authorization: Bearer <firebase-id-token>`.
Verification happens in `FirebaseAuthMiddleware` which:

1. Calls `firebase_admin.auth.verify_id_token(token, clock_skew_seconds=5)`.
2. Rejects the request with 401 on `InvalidIdTokenError` / `ExpiredIdTokenError`.
3. Rejects with 403 on missing `company_id` custom claim (multi-tenant anchor).
4. Attaches `request.state.{user_id, company_id, email}` for downstream.
5. `check_revoked=True` is **not** set globally — reserved for privileged
   routes only, per `.claude/rules/security.md` §1.

Per-route dependencies (`CurrentUser`) then surface the same data as a typed
`FirebaseUser` for handler signatures. Middleware + dependency are
complementary: the middleware blocks before a handler is even picked (cheap
rejection, no ADK init), the dependency gives handlers a typed user.

---

## 2. API surface spec (full)

### 2.1 `POST /api/v1/triage`

| Field              | Value                                                                             |
| ------------------ | --------------------------------------------------------------------------------- |
| Auth               | Required (Firebase ID token with `company_id` claim)                              |
| Content-Type       | `application/json`                                                                |
| Request schema     | `TriageRequest` (see §3.1)                                                        |
| Response media     | `text/event-stream`                                                               |
| Response body      | SSE frames, see §3                                                                |
| Idempotency header | Optional `Idempotency-Key: <uuidv7>` — cached result replayed if seen in last 1 h |
| Rate limit         | 10 req/min/uid + 100 req/day/uid (slowapi, per §10)                               |
| Cloud Run timeout  | Service deployed with `--timeout=900` (15 min; well above P99 pipeline latency)  |

**Status codes (before the stream opens):**

| Code | When                                                                                  | Payload                               |
| ---- | ------------------------------------------------------------------------------------- | ------------------------------------- |
| 200  | Stream open — response begins emitting SSE frames                                     | —                                     |
| 400  | Request body fails basic schema (e.g. both `event_id` and `raw_content` given)        | `{"error":{"code":"bad_request",...}}`|
| 401  | Missing / expired / invalid Firebase ID token                                         | `{"error":{"code":"invalid_token"}}`  |
| 403  | Token valid but no `company_id` claim, or event belongs to different tenant           | `{"error":{"code":"forbidden"}}`      |
| 404  | `event_id` given but not found in this tenant's collection                            | `{"error":{"code":"not_found"}}`      |
| 413  | `raw_content` > 20 000 chars                                                          | `{"error":{"code":"payload_too_large"}}`|
| 422  | Pydantic validation error (FastAPI default, keep the shape)                           | `{"detail":[...]}`                    |
| 429  | Rate limit hit                                                                        | `{"error":{"code":"rate_limited"},"retry_after":NN}` |
| 503  | ADK session service / Firestore unreachable at startup of request                     | `{"error":{"code":"unavailable"}}`    |

**Errors during the stream** never change HTTP status (already 200). They are
emitted as an `error` SSE frame and the stream is closed cleanly with `done`.

**Example cURL (happy path):**

```bash
curl -N -X POST https://api.example.com/api/v1/triage \
  -H "Authorization: Bearer $ID_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: 01HT9F6WRY7J2K8X3C5V9N2Z4Q" \
  -d '{"event_id":"01HT9F4MXP1Y9QJ3BW2D8K5V7R"}'
```

The `-N` flag disables curl's own output buffering — without it you'll see
the stream only after it closes.

**Example cURL (raw_content fallback):**

```bash
curl -N -X POST https://api.example.com/api/v1/triage \
  -H "Authorization: Bearer $ID_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"raw_content":"Truck #T-887 broke down near Nashik, 400 boxes FMCG delayed 24h."}'
```

### 2.2 `GET /api/v1/exceptions`

| Field          | Value                                                                 |
| -------------- | --------------------------------------------------------------------- |
| Auth           | Required                                                              |
| Query params   | `page_size` (int, default 25, max 100), `cursor` (str, opaque)        |
| Response model | `Page[ExceptionSummary]` (see §6.1)                                   |
| Rate limit     | 60 req/min/uid                                                        |

**Status codes:**

| Code | When                                                         |
| ---- | ------------------------------------------------------------ |
| 200  | Normal response                                              |
| 400  | `page_size` out of range, malformed `cursor`                 |
| 401  | Missing / invalid token                                      |
| 403  | Token valid but no `company_id` claim                        |
| 429  | Rate limit                                                   |
| 503  | Firestore unavailable                                        |

**Example:**

```bash
curl "https://api.example.com/api/v1/exceptions?page_size=25" \
  -H "Authorization: Bearer $ID_TOKEN"
```

**Example with cursor:**

```bash
curl "https://api.example.com/api/v1/exceptions?page_size=25&cursor=01HT9F4MXP1Y9QJ3BW2D8K5V7R" \
  -H "Authorization: Bearer $ID_TOKEN"
```

### 2.3 `GET /api/v1/exceptions/{exception_id}`

| Field          | Value                          |
| -------------- | ------------------------------ |
| Auth           | Required                       |
| Path param     | `exception_id` (ULID/UUIDv7)   |
| Response model | `TriageResultPublic`           |

**Status codes:**

| Code | When                                                                 |
| ---- | -------------------------------------------------------------------- |
| 200  | Found                                                                |
| 401  | Missing / invalid token                                              |
| 403  | Exists but tenant mismatch (per §8 existence-before-permission it is still 403, intentional: tenant fence is the primary contract) |
| 404  | Doesn't exist                                                        |

### 2.4 Debug routes (dev/staging only)

`POST /api/v1/classify` and `POST /api/v1/impact` — the current runners
(`classifier_runner.py`, `impact_runner.py`) are lifted into route modules
(`runners/routes/debug.py`) and only included in the router when
`settings.ENV != "prod"`. Auth still applies; no SSE; single JSON response.

---

## 3. `POST /api/v1/triage` — the SSE contract in full

### 3.1 Request schema

```python
# modules/triage/models/api_envelopes.py  (extended)
class TriageRequest(BaseModel):
    """Input body for POST /api/v1/triage.

    Exactly one of ``event_id`` or ``raw_content`` must be present. The
    ``model_validator`` below enforces the XOR at parse time so handlers
    never see an invalid shape.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str | None = Field(
        default=None,
        min_length=20,
        max_length=40,
        description="ULID/UUIDv7 of an exception already persisted in Firestore.",
    )
    raw_content: str | None = Field(
        default=None,
        min_length=1,
        max_length=20_000,
        description="Free-text exception description for on-the-fly triage.",
    )
    locale: Literal["en-IN", "hi-IN", "en-US"] = "en-IN"

    @model_validator(mode="after")
    def _exactly_one_source(self) -> "TriageRequest":
        if bool(self.event_id) == bool(self.raw_content):
            msg = "Provide exactly one of event_id or raw_content (not both, not neither)."
            raise ValueError(msg)
        return self
```

The 20 000-char ceiling on `raw_content` is the API-level guardrail against
prompt-injection volume / cost. See §16 for the broader security rationale.

### 3.2 Response headers

```
HTTP/1.1 200 OK
Content-Type: text/event-stream; charset=utf-8
Cache-Control: no-cache, no-transform
Connection: keep-alive
X-Accel-Buffering: no
X-Correlation-Id: <uuidv7>
```

Why each header:

- `Content-Type: text/event-stream` — the MIME that makes browser
  `EventSource` accept the stream.
- `Cache-Control: no-cache, no-transform` — prevent any intermediary from
  buffering for cacheability checks.
- `Connection: keep-alive` — HTTP/1.1 explicit hint. Under HTTP/2 on Cloud
  Run this header is ignored by the protocol but harmless.
- `X-Accel-Buffering: no` — opt out of Nginx/Cloud-Run-Front-End buffering.
  This is the single header most likely to make the difference between "it
  works on localhost, batches in prod."
- `X-Correlation-Id` — bound by `AuditLogMiddleware` into structlog
  contextvars; exposed so clients can quote it in bug reports.

### 3.3 Event frame format

Each frame is:

```
event: <name>\n
data: <json-compact>\n
\n
```

- `<name>` is one of the seven names in §3.4.
- `<json-compact>` is one line (no embedded `\n` — SSE would treat an embedded
  LF as a new `data:` chunk). Use `json.dumps(..., separators=(",", ":"))`.
- Two trailing newlines are mandatory — they terminate the frame.

### 3.4 The seven event types

#### `agent_started`

Emitted when an ADK agent enters `Runner.run_async`.

```
event: agent_started
data: {"agent":"classifier","ts":"2026-04-18T10:00:00Z"}
```

Fields:
- `agent` — the ADK agent `name=` attribute.
- `ts` — ISO-8601 UTC, tz-aware (never naive).

#### `tool_invoked`

Emitted once per `FunctionCallEvent` at the moment the tool starts
executing. We also emit it with `duration_ms` on `FunctionResponseEvent`
(same frame name, distinguished by presence of `duration_ms`) — or keep them
separate by emitting `tool_started` / `tool_completed` if the UI wants both.
For Tier 1 we emit only the completion variant to keep the stream lean:

```
event: tool_invoked
data: {"tool":"get_exception_event","agent":"classifier_fetcher","duration_ms":12,"ts":"2026-04-18T10:00:01Z"}
```

#### `agent_completed`

Emitted when an ADK agent's `Runner.run_async` closes its generator.

```
event: agent_completed
data: {"agent":"classifier","duration_ms":2150,"tokens_in":1240,"tokens_out":480,"ts":"2026-04-18T10:00:03Z"}
```

Tokens come from `event.usage_metadata` when present. Missing metadata is
logged but not fatal.

#### `partial_result`

Emitted the moment `state["triage:classification"]` is written (between the
classifier's completion and the impact agent's start). This is the UI's cue
to render the classification card even though `impact` is still running.

```
event: partial_result
data: {"classification":{"event_id":"…","category":"carrier_capacity_failure","severity":"HIGH","confidence":0.91,"reasoning":"…"}}
```

Only one `partial_result` per run (Tier 1). Tier 2 may add intermediate ones
when the Resolution Generator's judge loop iterates.

#### `complete`

Emitted exactly once — the final assembled `TriageResult`.

```
event: complete
data: {"triage_result":{"event_id":"…","status":"completed","classification":{…},"impact":{…},"summary":"…","processing_time_ms":4920,"errors":[]}}
```

If `impact` failed gracefully, it is `null` and `status` becomes
`"partial"`. `errors` lists the failure classification strings.

#### `error`

Emitted on any caught failure. Does NOT terminate the stream — `complete`
and `done` still follow.

```
event: error
data: {"code":"IMPACT_UNAVAILABLE","message":"Impact agent returned no output","recoverable":true,"ts":"2026-04-18T10:00:05Z"}
```

Error codes follow the canonical list in §7.3.

#### `done` (terminator)

The final frame. Its `data` line is the literal sentinel `[DONE]` (OpenAI
convention — easy for simple JS clients to detect string equality).

```
event: done
data: [DONE]
```

After `done`, the async generator returns. Starlette closes the HTTP body,
the TCP connection stays open for any keep-alive. The browser's
`EventSource` will try to reconnect unless we close the connection — see
§3.6.

### 3.5 Event ordering guarantee

```
agent_started(classifier)
  [ tool_invoked* | agent_started/completed of sub-agents ]*
agent_completed(classifier)
partial_result
agent_started(impact)
  [ tool_invoked* | ... ]*
agent_completed(impact)
complete
done
```

Orderings violated under known failure modes:
- **Classifier fails:** `agent_started(classifier)`, `error`, `complete`
  (with `classification=null`, `impact=null`, `status="failed"`), `done`.
  No `partial_result`. No impact events.
- **Impact fails:** full classifier stream, `partial_result`,
  `agent_started(impact)`, `error`, `complete` (with `impact=null`,
  `status="partial"`), `done`.

Client state machines should be built from this contract, not from the
happy path alone. See §12 for a reference consumer.

### 3.6 Reconnection — `Last-Event-ID` handling

Per the HTML spec, on connection drop the browser's `EventSource` attempts
reconnection and sends `Last-Event-ID: <id>` if the server attached `id:`
lines to prior events.

**Tier 1 policy: stateless — do not resume.** We do not emit `id:` lines,
so the client's `Last-Event-ID` is always empty, and reconnection starts
the pipeline fresh. Rationale: the triage pipeline is not idempotent on
Gemini cost, and re-running on reconnect is cheaper to reason about than
replaying a partially-persisted ADK session. The cost cap lives at the
rate limiter.

**Tier 3 upgrade path** (deferred): persist the event stream to Firestore
keyed by `Idempotency-Key`, emit `id:` lines (`id: 3\n` before each frame),
and on reconnect replay frames with `id > Last-Event-ID` before continuing.
Flagged for when dashboard clients go mobile.

If the client sends `Last-Event-ID`, we log it (for debugging) and ignore
it — the stream starts fresh.

### 3.7 Keep-alive comments

The stream emits `:\n\n` (empty SSE comment) every 15 s if no real frame
has been sent. This pushes a TCP packet through intermediaries that would
otherwise time the connection out. The SSE comment starts with `:` and the
browser ignores it entirely.

Implementation pattern: wrap the generator in an outer `asyncio.wait_for`
loop with a 15 s timeout that emits the heartbeat and resumes. See §4.

---

## 4. Streaming runner implementation skeleton

This section is ready-to-paste (with minor adaptation to your settings /
session-service import). It lives at
`src/supply_chain_triage/runners/routes/triage.py`.

```python
"""POST /api/v1/triage — SSE endpoint running the classifier→impact pipeline."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from google.adk.events import Event
from google.adk.runners import Runner
from google.genai import types as genai_types

from supply_chain_triage.core.config import Settings, get_settings
from supply_chain_triage.middleware.audit_log import audit_event
from supply_chain_triage.middleware.firebase_auth import CurrentUser, FirebaseUser
from supply_chain_triage.modules.triage.agents.classifier.agent import create_classifier
from supply_chain_triage.modules.triage.agents.impact.agent import create_impact
from supply_chain_triage.modules.triage.memory.session import build_session_service
from supply_chain_triage.modules.triage.models.api_envelopes import TriageRequest
from supply_chain_triage.modules.triage.models.triage_result import TriageResult
from supply_chain_triage.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["triage"])

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

HEARTBEAT_INTERVAL_S = 15.0


# ---------- public route ----------

@router.post("/triage")
async def triage_exception(
    *,
    request: Request,
    current_user: CurrentUser,
    payload: TriageRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> StreamingResponse:
    """Run the triage pipeline and stream progress as Server-Sent Events.

    The HTTP connection switches to ``text/event-stream`` immediately; any
    failure after that is signalled by an ``error`` SSE frame, never by an
    HTTP status code change.
    """
    # Pre-flight (still under 200-before-stream): reject obvious mismatches now.
    if payload.event_id is not None:
        await _assert_tenant_owns_event(
            event_id=payload.event_id,
            company_id=current_user.company_id,
            settings=settings,
        )

    generator = _sse_pipeline(
        request=request,
        payload=payload,
        user=current_user,
    )
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


# ---------- generator ----------

async def _sse_pipeline(
    *,
    request: Request,
    payload: TriageRequest,
    user: FirebaseUser,
) -> AsyncIterator[bytes]:
    """Top-level generator: wraps heartbeat + hands off to pipeline driver."""
    correlation_id = request.state.correlation_id
    audit_event(
        "agent_invoked",
        correlation_id=correlation_id,
        user_id=user.user_id,
        company_id=user.company_id,
        agent_name="triage_pipeline",
    )
    pipeline_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
    driver = asyncio.create_task(_drive_pipeline(payload, user, pipeline_queue))

    try:
        while True:
            try:
                frame = await asyncio.wait_for(
                    pipeline_queue.get(), timeout=HEARTBEAT_INTERVAL_S
                )
            except asyncio.TimeoutError:
                yield b":\n\n"  # heartbeat
                continue
            if frame is None:  # sentinel — pipeline done
                break
            # Cooperative disconnect check between frames.
            if await request.is_disconnected():
                logger.info("sse_client_disconnect", correlation_id=correlation_id)
                driver.cancel()
                break
            yield frame
    except asyncio.CancelledError:
        # Upstream cancel (client hangup reaches the ASGI layer). Propagate.
        driver.cancel()
        raise
    finally:
        # Always await the driver so its `finally:` blocks run (session cleanup).
        try:
            await driver
        except (asyncio.CancelledError, Exception):  # noqa: BLE001 — swallow on teardown only
            pass
        audit_event(
            "agent_completed",
            correlation_id=correlation_id,
            user_id=user.user_id,
            company_id=user.company_id,
            agent_name="triage_pipeline",
        )


async def _drive_pipeline(
    payload: TriageRequest,
    user: FirebaseUser,
    q: asyncio.Queue[bytes | None],
) -> None:
    """Run classifier then impact; push SSE frames onto the queue."""
    started = time.monotonic()
    session_service = build_session_service()  # your FirestoreSessionService
    classifier_agent = create_classifier()
    impact_agent = create_impact()

    classifier_ok = False
    classification: dict[str, Any] | None = None

    try:
        # --- Classifier ---
        await q.put(_frame("agent_started", {"agent": "classifier", "ts": _now()}))
        session = await session_service.create_session(
            app_name="triage", user_id=user.user_id
        )
        message = _build_message(payload)
        classifier_tokens = {"in": 0, "out": 0}
        classifier_started_ms = time.monotonic()
        runner = Runner(
            agent=classifier_agent,
            app_name="triage",
            session_service=session_service,
        )
        async for event in runner.run_async(
            user_id=user.user_id, session_id=session.id, new_message=message
        ):
            async for frame in _map_adk_event(event, classifier_tokens):
                await q.put(frame)
        classifier_duration_ms = int((time.monotonic() - classifier_started_ms) * 1000)
        await q.put(
            _frame(
                "agent_completed",
                {
                    "agent": "classifier",
                    "duration_ms": classifier_duration_ms,
                    "tokens_in": classifier_tokens["in"],
                    "tokens_out": classifier_tokens["out"],
                    "ts": _now(),
                },
            )
        )

        # Pull classification out of state; skip impact if missing (hard-fail mode).
        state = (await session_service.get_session(
            app_name="triage", user_id=user.user_id, session_id=session.id
        )).state
        classification = state.get("triage:classification")
        if classification is None:
            await q.put(_frame("error", {
                "code": "CLASSIFICATION_MISSING",
                "message": "Classifier returned no structured output.",
                "recoverable": False,
                "ts": _now(),
            }))
        else:
            classifier_ok = True
            await q.put(_frame("partial_result", {"classification": classification}))

        # --- Impact (only if classifier produced something) ---
        impact: dict[str, Any] | None = None
        if classifier_ok:
            await q.put(_frame("agent_started", {"agent": "impact", "ts": _now()}))
            impact_tokens = {"in": 0, "out": 0}
            impact_started_ms = time.monotonic()
            runner_i = Runner(
                agent=impact_agent,
                app_name="triage",
                session_service=session_service,
            )
            try:
                async for event in runner_i.run_async(
                    user_id=user.user_id, session_id=session.id, new_message=message
                ):
                    async for frame in _map_adk_event(event, impact_tokens):
                        await q.put(frame)
                impact_duration_ms = int((time.monotonic() - impact_started_ms) * 1000)
                await q.put(
                    _frame(
                        "agent_completed",
                        {
                            "agent": "impact",
                            "duration_ms": impact_duration_ms,
                            "tokens_in": impact_tokens["in"],
                            "tokens_out": impact_tokens["out"],
                            "ts": _now(),
                        },
                    )
                )
                state = (await session_service.get_session(
                    app_name="triage", user_id=user.user_id, session_id=session.id
                )).state
                impact = state.get("triage:impact")
                if impact is None:
                    await q.put(_frame("error", {
                        "code": "IMPACT_UNAVAILABLE",
                        "message": "Impact agent returned no structured output.",
                        "recoverable": True,
                        "ts": _now(),
                    }))
            except Exception as exc:  # noqa: BLE001 — final guardrail; classification survives
                logger.exception("impact_failed")
                await q.put(_frame("error", {
                    "code": "IMPACT_UNAVAILABLE",
                    "message": str(exc)[:200],
                    "recoverable": True,
                    "ts": _now(),
                }))

        # --- Final assembly ---
        result = TriageResult(
            event_id=payload.event_id or "",
            status="completed" if (classifier_ok and impact) else "partial" if classifier_ok else "failed",
            classification=classification,
            impact=impact,
            summary=_summary(classification, impact),
            processing_time_ms=int((time.monotonic() - started) * 1000),
            errors=[],
        )
        await q.put(_frame("complete", {"triage_result": result.model_dump(mode="json")}))
        await q.put(_DONE)

    except asyncio.CancelledError:
        # Client hung up. Do NOT emit any more frames — queue consumer is gone.
        raise
    except Exception as exc:  # noqa: BLE001 — catch-all for unexpected failure
        logger.exception("triage_pipeline_unhandled")
        await q.put(_frame("error", {
            "code": "INTERNAL",
            "message": "Internal error during triage.",
            "recoverable": False,
            "ts": _now(),
        }))
        await q.put(_DONE)
    finally:
        await q.put(None)  # sentinel to close the outer loop


# ---------- helpers ----------

def _frame(event: str, data: dict[str, Any]) -> bytes:
    """Serialize one SSE frame to bytes."""
    body = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    return f"event: {event}\ndata: {body}\n\n".encode("utf-8")


_DONE = b"event: done\ndata: [DONE]\n\n"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _build_message(payload: TriageRequest) -> genai_types.Content:
    text = (
        f"Classify exception with event_id: {payload.event_id}"
        if payload.event_id
        else f"Classify this exception description: {payload.raw_content}"
    )
    return genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=text)])


async def _map_adk_event(event: Event, tokens: dict[str, int]) -> AsyncIterator[bytes]:
    """Translate one ADK event into 0..N SSE frames. See §5 for the full table."""
    # Token accounting
    um = getattr(event, "usage_metadata", None)
    if um is not None:
        tokens["in"] += getattr(um, "prompt_token_count", 0) or 0
        tokens["out"] += getattr(um, "candidates_token_count", 0) or 0

    # Function call: record tool invocation (started)
    function_calls = event.get_function_calls() if hasattr(event, "get_function_calls") else []
    for fc in function_calls:
        yield _frame("tool_invoked", {
            "tool": fc.name,
            "agent": event.author or "unknown",
            "ts": _now(),
            "phase": "started",
        })

    # Function response: record tool completion with duration (if ADK supplies it)
    function_responses = (
        event.get_function_responses() if hasattr(event, "get_function_responses") else []
    )
    for fr in function_responses:
        yield _frame("tool_invoked", {
            "tool": fr.name,
            "agent": event.author or "unknown",
            "ts": _now(),
            "phase": "completed",
        })


def _summary(classification: dict | None, impact: dict | None) -> str:
    if classification is None:
        return "Triage failed before classification."
    base = f"Category: {classification.get('category')}; Severity: {classification.get('severity')}."
    if impact is None:
        return base + " Impact assessment unavailable."
    return base + f" Estimated delay: {impact.get('delay_hours', '?')}h."


async def _assert_tenant_owns_event(*, event_id: str, company_id: str, settings: Settings) -> None:
    """404 if event not in tenant's collection; 403 intentionally collapsed to 404-like."""
    # Implementation lives in modules/triage/memory/exception_events.py
    from supply_chain_triage.modules.triage.memory.exception_events import (
        fetch_event_for_tenant,
    )
    event = await fetch_event_for_tenant(event_id=event_id, company_id=company_id)
    if event is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found"}})
```

**Design notes on the skeleton:**

- **Producer-consumer with a queue.** The outer generator owns the HTTP
  response; the inner `_drive_pipeline` task pushes frames on a queue. This
  lets the outer loop apply heartbeats and `is_disconnected()` checks
  independently of how slow the pipeline runs.
- **`asyncio.wait_for(queue.get(), timeout=15)`** is the heartbeat
  mechanism — if nothing came from the pipeline for 15 s, yield `:\n\n`.
- **Cancellation.** If `request.is_disconnected()` returns True, we
  `driver.cancel()` and break out; the driver's `finally:` runs and the
  session is closed. ASGI layer cancellation (upstream timeout, ALB drop)
  raises `asyncio.CancelledError` in the outer loop — we re-raise after
  cancelling the driver.
- **Never `raise HTTPException` after the first `yield`.** Starlette has
  already written `200 OK\r\n` headers. The only way to signal failure is an
  `error` frame followed by `done`.

---

## 5. ADK Runner event mapping table

`Runner.run_async` yields `google.adk.events.Event` instances. Each carries
a subset of: `author` (agent name), `content` (Gemini `types.Content`),
`partial` (bool — streaming tokens), `turn_complete`, `interrupted`, and
convenience accessors `get_function_calls()` / `get_function_responses()`.
`usage_metadata` (prompt/candidate token counts) is attached on model
completion events.

| ADK event shape                                                    | Our SSE event          | Data fields emitted                                         | Notes                                                       |
| ------------------------------------------------------------------ | ---------------------- | ----------------------------------------------------------- | ----------------------------------------------------------- |
| First event with `author=="classifier"` (agent begin)              | `agent_started`        | `agent, ts`                                                 | We emit this explicitly **before** invoking the runner; ADK itself doesn't have a dedicated "agent-started" event type. |
| Event with `get_function_calls()` non-empty                        | `tool_invoked` (phase: started)  | `tool, agent, ts, phase:"started"`                | One frame per call in the batch; ADK executes them in parallel. |
| Event with `get_function_responses()` non-empty                    | `tool_invoked` (phase: completed) | `tool, agent, ts, phase:"completed"`             | Duration derived from our own wall-clock; ADK doesn't pass per-tool ms natively. |
| Event with `content.parts[*].text` + `partial=True`                | **dropped**            | —                                                           | `.claude/rules/agents.md` §10: never stream intermediate token chunks from a SequentialAgent — it leaks raw JSON. |
| Event with `event.is_final_response()==True` (classifier)          | `agent_completed`, then `partial_result` | `agent, duration_ms, tokens_in, tokens_out` then `classification` object from state | Emit `partial_result` only after reading `state["triage:classification"]`. |
| Event with `event.is_final_response()==True` (impact)              | `agent_completed`      | `agent, duration_ms, tokens_in, tokens_out`                 | —                                                           |
| Event with `actions.state_delta` non-empty                         | **dropped**            | —                                                           | Consumed via `session_service.get_session(...).state` after the runner drains; no need to re-emit. |
| Event with `error_code`/`error_message` (ADK propagated failure)   | `error`                | `code, message, recoverable`                                | Map ADK `error_code` → our canonical codes (§7.3). |
| Event with `interrupted=True`                                      | `error`                | `code:"INTERRUPTED", message, recoverable:false`            | Rare — usually tool cap or safety block. |

**Token accounting:** ADK's `event.usage_metadata.prompt_token_count` and
`.candidates_token_count` are accumulated per agent in the `_map_adk_event`
helper. They're the source of truth for the `tokens_in`/`tokens_out` fields
in `agent_completed`.

**What we *don't* map:**

- **Raw Gemini streaming deltas** (`partial=True`). For a `SequentialAgent`
  pipeline, the classifier and impact agents both produce structured JSON
  output — streaming their JSON character-by-character would mean the UI
  sees `{"categor` before it sees `"carrier_capacity_failure"`. Tier 2's
  Resolution Generator may re-enable token streaming for the prose-summary
  step; Tier 1 does not.
- **`state_delta` events.** We read state once after each sub-agent
  completes. Emitting intermediate state leaks internal keys and shapes.

**Reference:** ADK Events and Event Loop docs (see Sources).

---

## 6. `GET /api/v1/exceptions` spec

### 6.1 Response model

```python
# modules/triage/models/api_envelopes.py
class ExceptionSummary(BaseModel):
    """Compact row for the dashboard list."""

    model_config = ConfigDict(extra="forbid")
    event_id: str
    company_id: str
    created_at: datetime
    status: Literal["pending", "completed", "partial", "failed"]
    category: str | None = None
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] | None = None
    summary: str | None = Field(default=None, max_length=300)


# in core/api_models.py (already called for by .claude/rules/models.md §6):
class Page[T](BaseModel):
    model_config = ConfigDict(extra="forbid")
    data: list[T]
    count: int          # count of rows in this page (not total)
    next_cursor: str | None = None
```

Response body example:

```json
{
  "data": [
    {
      "event_id": "01HT9F4MXP1Y9QJ3BW2D8K5V7R",
      "company_id": "acme",
      "created_at": "2026-04-18T09:55:12Z",
      "status": "completed",
      "category": "carrier_capacity_failure",
      "severity": "HIGH",
      "summary": "Truck breakdown near Nashik, 400 boxes delayed 24h."
    }
  ],
  "count": 1,
  "next_cursor": "01HT9F4MXP1Y9QJ3BW2D8K5V7R"
}
```

### 6.2 Cursor pagination vs offset

Per `.claude/rules/firestore.md` §5: **cursor only.** Firestore bills for
every doc skipped by `offset=N`; cursors scan from the index only. Our
cursor is the `exception_id` of the last returned row (opaque to the
client). The route handler does:

```python
@router.get("/exceptions", response_model=Page[ExceptionSummary])
async def list_exceptions(
    db: FirestoreDep,
    current_user: CurrentUser,
    page_size: int = 25,
    cursor: str | None = None,
) -> Any:
    """List this tenant's exceptions, newest first."""
    if not 1 <= page_size <= 100:
        raise HTTPException(400, "page_size out of range")

    base = (
        db.collection("exceptions")
          .where(filter=FieldFilter("company_id", "==", current_user.company_id))
          .order_by("created_at", direction="DESCENDING")
          .limit(page_size)
    )
    if cursor:
        anchor = await db.collection("exceptions").document(cursor).get()
        if not anchor.exists:
            raise HTTPException(400, "invalid cursor")
        base = base.start_after(anchor)

    rows = [
        ExceptionSummary.model_validate(doc.to_dict() | {"event_id": doc.id})
        async for doc in base.stream()
    ]
    next_cursor = rows[-1].event_id if len(rows) == page_size else None
    return Page[ExceptionSummary](data=rows, count=len(rows), next_cursor=next_cursor)
```

### 6.3 Firestore composite index

`firestore.indexes.json` must include:

```json
{
  "collectionGroup": "exceptions",
  "queryScope": "COLLECTION",
  "fields": [
    {"fieldPath": "company_id", "order": "ASCENDING"},
    {"fieldPath": "created_at", "order": "DESCENDING"}
  ]
}
```

Deployed via `firebase deploy --only firestore:indexes`. Without this
index, the query fails with `FAILED_PRECONDITION` at runtime.

### 6.4 Tenant-scope enforcement

- **Middleware** rejects missing `company_id` claim before the handler runs.
- **Route handler** includes `where("company_id", "==", current_user.company_id)`
  unconditionally.
- **Single-resource read** (`GET /exceptions/{id}`) fetches by ID and
  returns 403 on tenant mismatch — per `.claude/rules/security.md` §8:
  existence (404) before permission (403).

### 6.5 `page_size` limits

- Default: 25.
- Max: 100. Above returns 400. Rationale: each row already includes
  `summary` up to 300 chars, and Firestore list-endpoint cost scales
  linearly with page size.

---

## 7. Error model

### 7.1 Unified JSON envelope (non-SSE paths)

```json
{
  "error": {
    "code": "not_found",
    "message": "Exception not found",
    "request_id": "01HT9F6WRY7J2K8X3C5V9N2Z4Q"
  }
}
```

- `code` — short, lowercase, underscore-separated; stable for clients to
  switch on.
- `message` — human-readable, **no PII, no internal details**. Per
  `.claude/rules/api-routes.md` §9.
- `request_id` — the per-request correlation UUID (same as
  `X-Correlation-Id` response header).

An exception handler attached at app level normalizes `HTTPException` and
Pydantic `ValidationError` into this shape:

```python
@app.exception_handler(HTTPException)
async def _http_exc(request: Request, exc: HTTPException) -> JSONResponse:
    code = exc.detail if isinstance(exc.detail, str) else "error"
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {
            "code": code,
            "message": exc.detail if isinstance(exc.detail, str) else "Request failed",
            "request_id": getattr(request.state, "correlation_id", None),
        }},
    )
```

### 7.2 Canonical HTTP codes (mirrors `.claude/rules/api-routes.md` §8)

| Code | When                                                                        |
| ---- | --------------------------------------------------------------------------- |
| 400  | Malformed request, mutually exclusive fields, range errors                  |
| 401  | Missing / expired / invalid Firebase token                                  |
| 403  | No `company_id` claim, tenant mismatch                                      |
| 404  | Event ID not found                                                          |
| 409  | (future) duplicate triage for same `Idempotency-Key`                        |
| 413  | `raw_content` too large                                                     |
| 422  | Pydantic validation (FastAPI default)                                       |
| 429  | Rate limit                                                                  |
| 500  | Never intentional — but mapped if an unhandled exception escapes            |
| 503  | Dependency unavailable (Firestore, Gemini)                                  |

### 7.3 SSE `error` frame codes

These are a **separate taxonomy** from HTTP codes — they describe failures
that happen *during* a running pipeline.

| `code`                    | Meaning                                                      | `recoverable` |
| ------------------------- | ------------------------------------------------------------ | ------------- |
| `CLASSIFICATION_MISSING`  | Classifier completed but produced no structured output       | false         |
| `CLASSIFICATION_INVALID`  | Classifier output failed Pydantic validation                 | false         |
| `IMPACT_UNAVAILABLE`      | Impact agent failed; classification preserved                | true          |
| `TOOL_FAILED`             | A specific tool returned `{"status":"error", ...}`           | true          |
| `GEMINI_SAFETY_BLOCK`     | Safety filter tripped                                        | false         |
| `GEMINI_QUOTA_EXHAUSTED`  | Out of tokens / 429 from Gemini                              | false         |
| `INTERRUPTED`             | ADK interrupted (timeout, cap)                               | false         |
| `INTERNAL`                | Unclassified unexpected failure                              | false         |

`recoverable:true` means the stream will still emit `complete` with a
partial result. `recoverable:false` means the stream emits `complete` with
`status:"failed"`.

### 7.4 Error frames are advisory, `complete` is authoritative

Clients **must** wait for `complete` before deciding the final status — an
earlier `error` frame does not imply the whole run failed. This keeps the
terminal-state decision in one place on the consumer side.

---

## 8. Middleware stack

Per `.claude/rules/security.md` §9 (Risk 11 guard), the order is fixed.
Starlette wraps middlewares in **reverse** of `add_middleware` call order,
so the **last** added is the **outermost**.

```python
def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan, default_response_class=JSONResponse)

    # --- MIDDLEWARE STACK ORDER — Risk 11 regression guard ---
    # Canonical: trusted-host → CORS → auth → rate-limit → audit-log → routes
    # Starlette applies these in reverse of add order, so LAST add = OUTERMOST.

    # 5. Audit log — must see the authenticated user and the final outcome.
    app.add_middleware(AuditLogMiddleware)

    # 4. Rate limit — must run after auth to key on request.state.user_id.
    #    slowapi is wired as a route-decorator + global exception handler,
    #    NOT as a BaseHTTPMiddleware. See §10. The effective ordering still
    #    puts its check after Firebase auth because the limiter runs inside
    #    the route resolution, which happens after all BaseHTTPMiddleware.

    # 3. Firebase Auth — rejects unauth'd requests before any downstream work.
    app.add_middleware(FirebaseAuthMiddleware, public_paths=frozenset({"/health", "/ready", "/version"}))

    # 2. Input sanitization (§16) — Unicode-preserving HTML/control strip.
    app.add_middleware(InputSanitizationMiddleware)

    # 1b. CORS — must run BEFORE auth so preflight OPTIONS doesn't need credentials.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "Last-Event-ID"],
        expose_headers=["X-Correlation-Id"],
        max_age=600,
    )

    # 1a. Trusted host — outermost filter; reject bad Host headers cheaply.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.TRUSTED_HOSTS)

    # 6. Security headers are applied last in code (so they wrap responses first).
    app.add_middleware(SecurityHeadersMiddleware)

    # --- Routes ---
    app.include_router(triage.router)
    app.include_router(exceptions.router)
    if settings.ENV != "prod":
        app.include_router(debug.router)

    return app
```

**Effective inbound order (outermost → innermost):**

1. `SecurityHeadersMiddleware` (response-only effect; outermost wrap)
2. `TrustedHostMiddleware`
3. `CORSMiddleware`
4. `InputSanitizationMiddleware`
5. `FirebaseAuthMiddleware`
6. `AuditLogMiddleware`
7. Route (with slowapi `@limiter.limit(...)` decorator inside)

**A regression test** at
`tests/unit/middleware/test_stack_order.py` introspects
`app.user_middleware` and asserts the class-by-class order. Per §9 of the
security rules, this is the Risk-11 regression guard — not to be edited
without an ADR.

### 8.1 SSE + middleware gotchas

- **Gzip is banned globally.** Any gzip middleware that buffers the full
  response body breaks SSE. We do not install one.
- **`BaseHTTPMiddleware` wraps the response in a `StreamingResponse` around
  a `MemoryObjectReceiveStream`.** This generally works for SSE, but any
  middleware that attempts `await response.body` (reading the full body)
  collapses streaming to batch. Our custom middlewares never touch
  `response.body`.
- **`CORSMiddleware` is compatible with SSE** — it only sets response
  headers and handles preflight. No body access.

---

## 9. Auth middleware design

Two-layer design (matches `.claude/rules/api-routes.md` §5 + the
`firebase_auth.py` we already have):

### 9.1 Global middleware

`FirebaseAuthMiddleware` (already implemented) rejects unauth'd requests
early. Extensions to the current implementation:

```python
class FirebaseAuthMiddleware(BaseHTTPMiddleware):
    CLOCK_SKEW_SECONDS = 5  # tolerate 5s drift (Firebase default 0; too strict)

    async def dispatch(self, request, call_next):
        if request.url.path in self.public_paths:
            return await call_next(request)

        token = _extract_bearer(request)
        if token is None:
            return _json_error(401, "missing_credentials", request)

        try:
            claims = firebase_auth.verify_id_token(
                token,
                clock_skew_seconds=self.CLOCK_SKEW_SECONDS,
                check_revoked=False,  # per security.md §1; revocation checked per-route when needed
            )
        except firebase_auth.ExpiredIdTokenError:
            return _json_error(401, "token_expired", request)
        except firebase_auth.InvalidIdTokenError:
            return _json_error(401, "invalid_signature", request)
        except firebase_auth.CertificateFetchError:
            return _json_error(503, "auth_unavailable", request)
        except Exception:
            return _json_error(401, "invalid_token", request)

        company_id = claims.get("company_id")
        if not company_id:
            return _json_error(403, "missing_company_claim", request)

        request.state.user_id = claims["uid"]
        request.state.company_id = company_id
        request.state.email = claims.get("email")
        structlog.contextvars.bind_contextvars(
            user_id=claims["uid"],
            company_id=company_id,
        )
        return await call_next(request)
```

### 9.2 Per-route dependency (typed)

```python
# middleware/firebase_auth.py (additions)
@dataclass(frozen=True, slots=True)
class FirebaseUser:
    user_id: str
    company_id: str
    email: str | None

async def get_current_user(request: Request) -> FirebaseUser:
    """Expose middleware-verified claims as a typed dependency."""
    # Middleware already rejected unauth'd; state fields are guaranteed present.
    return FirebaseUser(
        user_id=request.state.user_id,
        company_id=request.state.company_id,
        email=getattr(request.state, "email", None),
    )

CurrentUser = Annotated[FirebaseUser, Depends(get_current_user)]
```

### 9.3 Public key caching

Firebase Admin Python caches Google's public JWKS automatically (since
the `firebase-admin` refactor that added cache). We don't need to re-roll
it. First request after cache eviction has ~50 ms extra latency.

### 9.4 Clock skew

`clock_skew_seconds=5` — small enough to keep replay windows tight, big
enough to eat clock drift between Cloud Run and the client's device. The
Firebase SDK's default of 0 has generated production incidents when
devices' clocks are slow by a few seconds.

### 9.5 Revocation

`check_revoked=True` is **not** set globally — each call would add an RPC.
Apply it on a per-route basis for sensitive mutations (Tier 2+) via a
`require_check_revoked` dependency override. For Tier 1 `POST /api/v1/triage`
is a read-like op on Gemini; the revocation-latency tradeoff isn't worth
the RPC.

---

## 10. Rate limiting wiring

We use **slowapi** (already in deps). It is compatible with SSE
`StreamingResponse` because rate-limit rejection happens *before* the route
handler runs — 429 responses never interact with the stream.

### 10.1 Configuration

```python
# middleware/rate_limit.py
from slowapi import Limiter
from slowapi.util import get_remote_address

def _key(request: Request) -> str:
    """Prefer authenticated user_id, fall back to IP."""
    return getattr(request.state, "user_id", None) or get_remote_address(request)

limiter = Limiter(
    key_func=_key,
    storage_uri=settings.RATE_LIMIT_STORAGE_URI,  # "redis://..." in prod, "memory://" in dev
    default_limits=["200/hour"],
)
```

### 10.2 Per-route limits

| Route                                  | Limit                                    |
| -------------------------------------- | ---------------------------------------- |
| `POST /api/v1/triage`                  | `10/minute` + `100/day` per user         |
| `POST /api/v1/classify` (debug)        | `30/minute` per user (dev only)          |
| `POST /api/v1/impact` (debug)          | `30/minute` per user (dev only)          |
| `GET  /api/v1/exceptions`              | `60/minute` per user                     |
| `GET  /api/v1/exceptions/{id}`         | `120/minute` per user                    |
| `GET  /health`, `/ready`, `/version`   | `60/minute` per IP                       |

Applied at route level:

```python
@router.post("/triage")
@limiter.limit("10/minute;100/day")
async def triage_exception(...) -> StreamingResponse: ...
```

### 10.3 429 response shape

```json
{
  "error": {
    "code": "rate_limited",
    "message": "Rate limit exceeded: 10 per 1 minute",
    "request_id": "01HT9F6WRY7J2K8X3C5V9N2Z4Q"
  }
}
```

Headers:
- `Retry-After: NN` (seconds until oldest request expires)
- `X-RateLimit-Limit: 10`
- `X-RateLimit-Remaining: 0`
- `X-RateLimit-Reset: <unix-ts>`

### 10.4 Distributed backend

`storage_uri` must be a Memorystore (Redis) endpoint in staging/prod —
in-memory breaks when Cloud Run scales to zero or across instances. Local
dev can keep `memory://`. The pydantic-settings validator rejects
`memory://` when `ENV != "dev"`.

---

## 11. CORS configuration

### 11.1 Settings

```python
# core/config.py
class Settings(BaseSettings):
    CORS_ORIGINS: list[str] = []

    @field_validator("CORS_ORIGINS")
    @classmethod
    def _no_wildcards_in_prod(cls, v, info):
        if info.data.get("ENV") in {"staging", "prod"} and any("*" in o for o in v):
            raise ValueError("CORS_ORIGINS cannot contain wildcards in non-dev")
        return v
```

Per `.claude/rules/security.md` §11: no wildcards in prod/staging;
container fails to boot.

### 11.2 Middleware setup

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,        # exact origins only
    allow_credentials=True,                     # cookies / Authorization pass through
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Idempotency-Key",
        "Last-Event-ID",
    ],
    expose_headers=["X-Correlation-Id"],
    max_age=600,   # 10 min preflight cache
)
```

### 11.3 SSE-specific CORS notes

- **`EventSource` and CORS.** The browser's `EventSource` constructor
  accepts `{ withCredentials: true }` which triggers a credentialed CORS
  preflight. With `allow_credentials=True` and exact origins, this works.
- **`text/event-stream` does not trigger a preflight by itself** (it's a
  "simple" response type from the browser's perspective). Preflight only
  fires because we send `Authorization: Bearer` — a non-simple header.
- **`Access-Control-Allow-Origin` must be set on the SSE response too.**
  Starlette's `CORSMiddleware` sets it on all responses including
  `StreamingResponse`; we don't need special handling.
- **`expose_headers` is important** so the client's JS can read
  `X-Correlation-Id` off the SSE response for logging.

### 11.4 CSP connect-src

Per `.claude/rules/security.md` §5, the Tier 3 React origin must list our
API origin in `connect-src`. The SSE `EventSource` request obeys
`connect-src`, not `script-src` or `frame-src`.

---

## 12. Client-side consumption pattern

Minimal TypeScript consumer using the native `EventSource`. Works in any
React/Vue/Svelte setup — the SSE contract is UI-framework-agnostic.

```ts
// client/triage.ts
type TriageEvent =
  | { type: "agent_started"; agent: string; ts: string }
  | { type: "tool_invoked"; tool: string; agent: string; phase: "started" | "completed"; ts: string }
  | { type: "agent_completed"; agent: string; duration_ms: number; tokens_in: number; tokens_out: number }
  | { type: "partial_result"; classification: Classification }
  | { type: "complete"; triage_result: TriageResult }
  | { type: "error"; code: string; message: string; recoverable: boolean }
  | { type: "done" };

export interface TriageHandler {
  onClassification?(c: Classification): void;
  onFinal?(t: TriageResult): void;
  onError?(code: string, message: string, recoverable: boolean): void;
  onLifecycle?(event: TriageEvent): void;
}

export async function runTriage(
  request: { event_id?: string; raw_content?: string; locale?: string },
  handler: TriageHandler,
  opts: { idToken: string; baseUrl: string; signal?: AbortSignal } = {} as any,
): Promise<void> {
  // EventSource can't do POST. Use fetch() + a manual SSE parser for full control.
  const resp = await fetch(`${opts.baseUrl}/api/v1/triage`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${opts.idToken}`,
      "Content-Type": "application/json",
      "Accept": "text/event-stream",
    },
    body: JSON.stringify(request),
    signal: opts.signal,
  });
  if (!resp.ok || !resp.body) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(`triage failed: ${resp.status} ${JSON.stringify(err)}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // Split on frame terminator "\n\n".
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const raw = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const parsed = parseSseFrame(raw);
      if (!parsed) continue;
      if (parsed.event === "done") {
        handler.onLifecycle?.({ type: "done" } as TriageEvent);
        return;
      }
      dispatch(parsed.event, parsed.data, handler);
    }
  }
}

function parseSseFrame(raw: string): { event: string; data: string } | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith(":")) continue;            // SSE comment (heartbeat)
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (dataLines.length === 0) return null;
  return { event, data: dataLines.join("\n") };
}

function dispatch(event: string, data: string, handler: TriageHandler) {
  if (event === "done") return;
  if (data === "[DONE]") return;
  const parsed = JSON.parse(data);
  handler.onLifecycle?.({ type: event, ...parsed } as TriageEvent);
  if (event === "partial_result") handler.onClassification?.(parsed.classification);
  if (event === "complete") handler.onFinal?.(parsed.triage_result);
  if (event === "error") handler.onError?.(parsed.code, parsed.message, parsed.recoverable);
}
```

**Why `fetch + ReadableStream` instead of `EventSource`:**

- `EventSource` is GET-only. Our API is POST (the request body carries
  `event_id` / `raw_content`).
- `fetch` lets us pass `Authorization: Bearer <token>` cleanly.
- `AbortController.signal` gives explicit cancellation (crucial for React
  cleanup in `useEffect`).

**React useEffect shape:**

```ts
useEffect(() => {
  const ctrl = new AbortController();
  runTriage({ event_id }, {
    onClassification: (c) => setClassification(c),
    onFinal: (t) => setTriageResult(t),
    onError: (code, msg, rec) => setError({ code, msg, rec }),
  }, { idToken, baseUrl, signal: ctrl.signal }).catch(console.error);
  return () => ctrl.abort();
}, [event_id, idToken]);
```

---

## 13. Cloud Run SSE caveats

Extended list beyond the zettel:

### 13.1 Timeout

- **Default 5 min (300 s).** Most triage runs finish in < 10 s, but a
  classifier retry loop + impact retry loop + slow Firestore cold start
  can push past 60 s.
- **Set `--timeout=900`** (15 min) for the triage service. Max allowed is
  3 600 s (60 min).
- **Set explicitly in `deploy.sh`** — default of 300 is a silent latency
  cliff. The headers trio does not extend the timeout; it only keeps the
  connection alive within it.

### 13.2 Chunked transfer encoding

Cloud Run auto-selects chunked encoding when the response body is
streamed without a `Content-Length`. FastAPI's `StreamingResponse` never
sets `Content-Length`, so chunked is always on for SSE. No action needed.

### 13.3 HTTP/2 on Cloud Run

- **Enable end-to-end HTTP/2** with `--use-http2`. This unlocks
  multiplexing and is compatible with SSE.
- **SSE over HTTP/2 works** — modern browsers support it; the 6
  concurrent-SSE-per-origin limit from HTTP/1.1 is lifted.
- **Trailers are not used by SSE** — no action needed.

### 13.4 Buffering

- **`X-Accel-Buffering: no`** — the canonical opt-out. Cloud Run's
  front-end honors it as documented.
- **Do not put Cloud Run behind API Gateway for SSE.** API Gateway
  buffers. If you need API Gateway features (API keys, quotas), terminate
  SSE at a Cloud Run service reached directly; put other APIs behind
  Gateway.
- **Known symptom:** classifier classification card appears only at the
  end of the run instead of at ~2 s. The underlying cause is buffering —
  add the header and retest.

### 13.5 Cold starts

A cold container delays the first byte by 3–8 s. The browser sees no
activity. Mitigations (pick the cheapest that fits budget):
- `--min-instances=1` (~$5/mo per service) eliminates cold starts.
- Alternatively emit an immediate `:\n\n` heartbeat right after the
  `async def` enters — gives the browser a TTFB within ~200 ms post-cold.
  Does not reduce total latency.

### 13.6 Connection caps

- **Max concurrent requests per instance** default 80. Each SSE consumes
  one. If 100 dashboards open at once during a demo, either increase
  concurrency to 200 or rely on autoscaling. Triage is bound by Gemini
  latency, not CPU, so higher concurrency is safe.

### 13.7 Load-balancer keepalive

If a Global HTTP(S) LB sits in front of Cloud Run, its idle timeout
defaults to 30 s (Classic LB) / 10 min (newer). Set to ≥ `--timeout` to
match. Otherwise LB drops a healthy stream.

---

## 14. Testing SSE

### 14.1 `httpx.AsyncClient` with streaming

```python
# tests/integration/runners/test_triage_sse.py
import json

import pytest
from httpx import AsyncClient

@pytest.mark.integration
async def test_triage_emits_canonical_event_sequence(app, test_id_token, seeded_event_id):
    async with AsyncClient(app=app, base_url="http://test") as client:
        events: list[tuple[str, dict]] = []
        async with client.stream(
            "POST",
            "/api/v1/triage",
            json={"event_id": seeded_event_id},
            headers={"Authorization": f"Bearer {test_id_token}"},
        ) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            assert resp.headers["x-accel-buffering"] == "no"

            buffer = ""
            async for chunk in resp.aiter_text():
                buffer += chunk
                while "\n\n" in buffer:
                    frame, buffer = buffer.split("\n\n", 1)
                    event_name, data = _parse_frame(frame)
                    if event_name is None:
                        continue  # heartbeat
                    events.append((event_name, data))
                    if event_name == "done":
                        break
                if events and events[-1][0] == "done":
                    break

    names = [n for n, _ in events]
    assert names[0] == "agent_started"
    assert "agent_completed" in names
    assert "partial_result" in names
    assert names[-2] == "complete"
    assert names[-1] == "done"

def _parse_frame(raw: str) -> tuple[str | None, dict]:
    event = None
    data_lines: list[str] = []
    for line in raw.split("\n"):
        if line.startswith(":"):
            return (None, {})  # heartbeat
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].strip())
    if not data_lines:
        return (None, {})
    try:
        data = json.loads("\n".join(data_lines))
    except json.JSONDecodeError:
        data = {"raw": "\n".join(data_lines)}
    return (event, data)
```

### 14.2 What to assert

- **Order.** `partial_result` comes after first `agent_completed`, before
  the impact `agent_started`.
- **Headers.** `Cache-Control`, `X-Accel-Buffering`, `Content-Type`.
- **Terminator.** Last two events are `complete`, `done`.
- **Content.** `complete` carries a `TriageResult` that round-trips
  through Pydantic (`TriageResult.model_validate(data["triage_result"])`).
- **Error path.** With a patched impact agent that raises, the stream still
  emits `complete` (with `impact=null`) and `done`.

### 14.3 Client disconnect test

```python
@pytest.mark.integration
async def test_client_disconnect_cancels_driver(app, test_id_token, seeded_event_id):
    async with AsyncClient(app=app, base_url="http://test") as client:
        async with client.stream(
            "POST",
            "/api/v1/triage",
            json={"event_id": seeded_event_id},
            headers={"Authorization": f"Bearer {test_id_token}"},
        ) as resp:
            it = resp.aiter_raw()
            # Consume first chunk then abort.
            await anext(it)
            await resp.aclose()
        # Assertion: driver task was cancelled, session was closed.
        # (Use a spy or log-capture fixture to verify cleanup ran.)
```

### 14.4 Unit test for `_map_adk_event`

Pure-function mapping, no network needed — construct fake ADK `Event`
objects with `get_function_calls()` returning a stub, assert the emitted
frames.

### 14.5 Coverage discipline

- **Unit tests**: `_frame`, `_map_adk_event`, `_build_message`, model
  validators on `TriageRequest` — 100 %.
- **Integration tests**: the full stream against Firestore + Auth
  emulators with a mocked Gemini (deterministic fixture). 1-2 happy paths,
  1 impact-fails path, 1 classifier-fails path, 1 disconnect path.
- **Load tests** are Tier 2 scope — `locust` with 100 concurrent SSE
  consumers against a staging deploy.

---

## 15. Observability for streaming requests

Per `.claude/rules/observability.md`:

### 15.1 OTel span tree

```
HTTP POST /api/v1/triage             (span from opentelemetry-instrumentation-fastapi)
├── agent.classifier                 (manual child span wrapping the classifier Runner.run_async)
│   ├── tool.get_exception_event     (manual child span per tool call)
│   └── gemini.generate_content      (from google.genai's OTel integration, if enabled)
├── agent.impact
│   ├── tool.get_classification
│   └── gemini.generate_content
└── sse.stream                       (manual child span covering the generator lifetime)
```

Attributes on every agent span (minimum):

- `agent.name` (`"classifier"`, `"impact"`)
- `agent.model` (`"gemini-2.5-flash"`)
- `gen_ai.request.model`
- `gen_ai.usage.input_tokens`
- `gen_ai.usage.output_tokens`
- `exception.id`
- `company.id` (from `FirebaseUser`)

### 15.2 Correlation with logs

Every `get_logger(__name__).info(...)` call during the request auto-picks
up `correlation_id`, `user_id`, `company_id` from structlog contextvars
(bound in `AuditLogMiddleware` + `FirebaseAuthMiddleware`). Cloud Logging
auto-correlates with traces when the JSON renderer writes
`logging.googleapis.com/trace` (configured in `utils/logging.py`).

### 15.3 Per-frame log (audit)

One `sse_frame_emitted` audit event per frame:

```python
audit_event(
    "sse_frame_emitted",
    correlation_id=correlation_id,
    user_id=user.user_id,
    company_id=user.company_id,
    event_type=event_name,          # "agent_started" / "partial_result" / ...
    size_bytes=len(frame),
)
```

This is essential for debugging "browser saw only first 3 events" reports
— you can correlate the server side audit log with browser timestamps.

### 15.4 Cost attribution

`agent_completed` SSE frames carry `tokens_in` / `tokens_out`. Dashboards
aggregate these by `agent.name` per `company.id` per day. Gemini response
metadata is written to span attributes as well per `observability.md` §7.

### 15.5 SIGTERM flush

Cloud Run sends SIGTERM with a 10 s grace period before SIGKILL. Per
`observability.md` §3, register a SIGTERM handler to `tracer_provider.shutdown()`
so in-flight spans are flushed to Cloud Trace. Without this, ~5 % of
traces are lost on every scale-down.

### 15.6 Audit events for this endpoint

Canonical events emitted by `POST /api/v1/triage`:

| Event                  | When                                             |
| ---------------------- | ------------------------------------------------ |
| `request.start`        | AuditLogMiddleware entry                         |
| `auth_login`           | After successful `verify_id_token`               |
| `agent_invoked`        | Top of `_sse_pipeline`, `agent_name="triage_pipeline"` |
| `agent_invoked`        | Per-sub-agent (classifier, impact)               |
| `tool_invoked`         | Per-tool                                         |
| `classification_result`| When `partial_result` emitted                    |
| `agent_completed`      | Per-sub-agent                                    |
| `sse_frame_emitted`    | Per SSE frame                                    |
| `request.end`          | AuditLogMiddleware exit                          |

All use the `audit_event(...)` helper from `middleware/audit_log.py`
(which already enforces required keys).

---

## 16. Security considerations

### 16.1 Authenticated SSE only

- Every SSE endpoint sits behind `FirebaseAuthMiddleware` + `company_id`
  claim check. No anonymous streaming.
- Refused tokens return **401 before the stream opens** — we do NOT emit
  an SSE error for auth failure; the HTTP status is the right surface.

### 16.2 Request-size limits

- Body: **32 KB max** (FastAPI level via `request.body()` length check in
  a custom middleware or an explicit `Request.body()` + length check in
  the handler).
- `raw_content`: **20 000 chars max** (Pydantic `max_length`). 413 above.
- `event_id`: 20–40 chars (ULID/UUIDv7 bounds).
- Reject `Content-Type` other than `application/json` with 415.

### 16.3 Prompt-injection defence

- Content from `raw_content` is **never** interpolated into system
  prompts. It goes through `Part.from_text(text=...)` as a user turn,
  which Gemini isolates from the system prompt.
- A classifier `before_model_callback` applies the shared guardrail from
  `modules/triage/guardrails/input_guard.py` (strip prompt-override
  attempts, scan for classic `ignore previous instructions` patterns).

### 16.4 PII discipline

- `raw_content` is not logged (it's in the banned field list —
  `.claude/rules/logging.md` §5 + drop-processor backstop).
- SSE frames are logged by *event type and size*, not by payload.
- `partial_result` / `complete` payloads go to the wire to the caller
  but **not** into logs or traces. The `audit_event("sse_frame_emitted",
  …)` call only records `event_type` and `size_bytes`.

### 16.5 Output surface

- No direct Firestore / Firebase SDK types leak into SSE data. Every
  frame's `data:` is a `.model_dump(mode="json")` of a Pydantic model.
- No internal IDs beyond `event_id` (already client-known) and
  `correlation_id` (intentionally exposed).

### 16.6 Unicode sanitization

`InputSanitizationMiddleware` from `.claude/rules/security.md` §10
strips control chars + HTML tags from `raw_content` while preserving
Devanagari / Latin / CJK / emoji. Applied **before** Pydantic validation
so downstream sees already-cleaned text.

### 16.7 Denial-of-service vectors

- **Slow-consumer** attack: client opens SSE but reads slowly, holding
  server resources. Mitigations: Cloud Run `--timeout=900` caps total,
  per-instance concurrency cap, rate limit at 10/min/uid.
- **Large-body attack:** 32 KB request cap + 20 000-char `raw_content`.
- **Chatty client:** rate limiter at Memorystore is the real gate. An IP
  without a valid token can't even get past `FirebaseAuthMiddleware`.

### 16.8 Ban unknown content-types at SSE POST

```python
if request.headers.get("content-type", "").split(";")[0] != "application/json":
    raise HTTPException(415, "unsupported_media_type")
```

Prevents weird request smuggling or accidental form-urlencoded posts.

### 16.9 CSRF posture

- Browser SSE via POST uses `Authorization: Bearer` in a custom header,
  which browsers do not attach automatically — no CSRF surface.
- Cookies are **not** used for auth. `allow_credentials=True` permits
  them but we don't read any.

---

## 17. Concrete next-session task list

**File-by-file, in order. Every step respects the placement hook in
`.claude/hooks/check_placement.py`.**

### Phase 1 — App factory + routes plumbing

1. **Create** `src/supply_chain_triage/runners/app.py` (the FastAPI app
   factory). Mounts: middleware stack (§8), lifespan (Firestore client,
   session service, Secret Manager reads), routers, global exception
   handler (§7.1). ~120 lines.
2. **Move** the current `classifier_runner.py` / `impact_runner.py`
   bodies into `runners/routes/debug.py` as two `APIRouter` routes.
   Include only when `settings.ENV != "prod"`. Delete the old files
   (keeping git history for reference).

### Phase 2 — Models

3. **Extend** `modules/triage/models/api_envelopes.py` with
   `TriageRequest` (§3.1) + `ExceptionSummary` (§6.1).
4. **Add** `core/api_models.py` holding the generic `Page[T]`,
   `Message`, and `ErrorEnvelope` models.
5. **Add** `modules/triage/models/triage_public.py` with
   `TriageResultPublic` (same shape as `TriageResult` but without any
   internal-only fields — confirm none exist; likely a re-export).

### Phase 3 — Memory adapter

6. **Add** `modules/triage/memory/exception_events.py` with:
   - `fetch_event_for_tenant(event_id, company_id) -> ExceptionEvent | None`
   - `list_exceptions_for_tenant(company_id, page_size, cursor) -> tuple[list[ExceptionSummary], str | None]`
   - `fetch_triage_result(event_id, company_id) -> TriageResult | None`
7. **Deploy** the Firestore composite index
   (`infra/firestore.indexes.json` — §6.3) via
   `firebase deploy --only firestore:indexes`.

### Phase 4 — Auth + middleware enhancements

8. **Extend** `middleware/firebase_auth.py` with `FirebaseUser` dataclass
   + `get_current_user` dependency + `CurrentUser` alias (§9.2). Add
   `clock_skew_seconds=5` to `verify_id_token` call (§9.4). Rebind
   structlog contextvars with `user_id` + `company_id` after verify.
9. **Add** `middleware/security_headers.py` with `SecurityHeadersMiddleware`
   from `security.md` §5.
10. **Add** `middleware/input_sanitization.py` per `security.md` §10.
11. **Add** `tests/unit/middleware/test_stack_order.py` — asserts
    `app.user_middleware` order matches §8.

### Phase 5 — SSE endpoint

12. **Add** `runners/routes/triage.py` with the full generator from §4.
13. **Add** `runners/routes/exceptions.py` with both list and detail
    endpoints from §6.
14. **Register** all routers in `runners/app.py`.

### Phase 6 — Rate limiting

15. **Add** `middleware/rate_limit.py` with slowapi `Limiter` bound to
    Memorystore (§10). Wire the `429` exception handler.
16. **Settings field**: `RATE_LIMIT_STORAGE_URI` (default
    `memory://` in dev, `redis://...` otherwise). Validator in
    `core/config.py`.

### Phase 7 — Observability

17. **Extend** `utils/logging.py` with `log_sse_frame(event_type, size_bytes)`
    helper (typed wrapper around `audit_event("sse_frame_emitted", ...)`).
18. **Add** `core/tracing.py` with OTel `TracerProvider` configured for
    Cloud Trace (per `observability.md` §1-3). Register SIGTERM handler.

### Phase 8 — Tests

19. **Add** `tests/integration/runners/test_triage_sse.py` (§14.1-14.3).
20. **Add** `tests/unit/runners/test_frame_helpers.py` covering
    `_frame`, `_map_adk_event`, `_summary`.
21. **Add** `tests/unit/runners/test_triage_request.py` covering the
    `TriageRequest` XOR validator + 20 000-char cap.
22. **Add** `tests/integration/runners/test_exceptions_list.py` covering
    pagination + tenant scoping.

### Phase 9 — Deployment

23. **Update** `infra/firestore.indexes.json` with the composite index.
24. **Update** `scripts/deploy.sh` with `--timeout=900 --use-http2 --min-instances=1`
    flags and the `RATE_LIMIT_STORAGE_URI`/`CORS_ORIGINS` secrets.
25. **Update** `.env.template` with new required names:
    `RATE_LIMIT_STORAGE_URI`, `CORS_ORIGINS`, `TRUSTED_HOSTS`.

### Phase 10 — Validation handoff

26. **Exercise** the stream with the browser DevTools Network tab against
    a seeded event_id; verify:
    - Classification card renders at ~2-3 s (not at end-of-run).
    - `:` heartbeats are visible every 15 s if the pipeline stalls.
    - Disconnecting aborts the Gemini call on the server (check logs).
27. **Validation gate.** Present a matrix (happy path, classifier-fails,
    impact-fails, auth-missing, rate-limited, disconnect) + sample SSE
    traces to the user. Only after user validation does this feature
    ship.

**Rough time estimate** (ballpark): Phase 1-5 ≈ 1 day, Phase 6-8 ≈ 1 day,
Phase 9-10 ≈ half-day. Adjust per pair-coding pace.

---

## 18. Sources + dates (accessed 2026-04-18)

**FastAPI / SSE:**
- [FastAPI — Server-Sent Events](https://fastapi.tiangolo.com/tutorial/server-sent-events/)
- [FastAPI — StreamingResponse](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse)
- [sse-starlette (reference implementation — our choice is plain `StreamingResponse`)](https://github.com/sysid/sse-starlette)
- [sse-starlette — client disconnect detection](https://deepwiki.com/sysid/sse-starlette/3.5-client-disconnection-detection)
- [FastAPI discussion #14552 — streaming + disconnect](https://github.com/fastapi/fastapi/discussions/14552)
- [FastAPI issue #3766 — cancel handler on disconnect](https://github.com/fastapi/fastapi/issues/3766)

**Google ADK:**
- [ADK Events reference](https://google.github.io/adk-docs/events/)
- [ADK Streaming — event handling with `run_live`](https://google.github.io/adk-docs/streaming/dev-guide/part3/)
- [ADK Event Loop](https://google.github.io/adk-docs/runtime/event-loop/)
- [ADK Callbacks](https://google.github.io/adk-docs/callbacks/)

**Cloud Run:**
- [Configure request timeout](https://docs.cloud.google.com/run/docs/configuring/request-timeout)
- [ADK + Next.js SSE on Cloud Run — buffering issue thread](https://discuss.google.dev/t/google-adk-next-js-sse-streaming-stops-working-on-cloud-run/294138)
- [Cloud Run FAQ (ahmetb)](https://github.com/ahmetb/cloud-run-faq)

**SSE spec / `Last-Event-ID`:**
- [MDN — Using Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)
- [HTML Living Standard — §9.2 Server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html)

**Firebase Auth:**
- [Verify ID Tokens — Firebase Admin](https://firebase.google.com/docs/auth/admin/verify-id-tokens)
- [firebase-admin-python — `_token_gen.py` (clock skew param)](https://github.com/firebase/firebase-admin-python/blob/main/firebase_admin/_token_gen.py)
- [firebase-admin-python issue #624 — "token used too early"](https://github.com/firebase/firebase-admin-python/issues/624)

**Existing internal docs:**
- `docs/research/zettel-fastapi-sse-cloud-run.md` — the header-trio
  first-principles zettel this document extends.
- `.claude/rules/api-routes.md` — route-level conventions this doc aligns to.
- `.claude/rules/agents.md` §10 — "stream from final agent only" rule.
- `.claude/rules/security.md` §9 — Risk-11 middleware order.
- `.claude/rules/observability.md` — span + audit event contracts.
- `.claude/rules/firestore.md` §5 — cursor-only pagination rule.
- `.claude/rules/models.md` §6 — generic `Page[T]` shape.

---

**End of document.** Next action per the SDLC cycle: turn this research
into a Tier-1 API PRD for user approval, **then** start the Phase 1 file
scaffolding. No implementation before the PRD gate.

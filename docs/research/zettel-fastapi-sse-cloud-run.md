---
title: FastAPI SSE on Cloud Run — buffering pitfalls and the header trio
type: zettel
tags: [fastapi, sse, streaming, cloud-run, zettel]
status: first-principles
last_updated: 2026-04-14
confidence: medium
sources:
  - https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse
  - https://discuss.google.dev/t/fastapi-streamingresponse-on-cloud-run/182021
  - https://discuss.google.dev/t/streaming-responses-back-with-fastapi-and-api-gateway/186817
  - https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events
related:
  - "[[adr-004-streaming-strategy]]"
  - "[[Supply-Chain-Agent-Spec-Coordinator]]"
---

# FastAPI SSE on Cloud Run — buffering pitfalls and the header trio

> **TL;DR.** SSE from FastAPI to browser over Cloud Run works *if* you set three headers (`Cache-Control: no-cache`, `X-Accel-Buffering: no`, `Connection: keep-alive`), send a `: ping\n\n` keep-alive every 15s, and don't put Cloud Run behind API Gateway. Direct Cloud Run is fine; API Gateway buffers.

## First principles

**SSE is not a real-time protocol. It's an HTTP response that never ends.** The server sets `Content-Type: text/event-stream`, then keeps writing `event: name\ndata: payload\n\n` frames. The browser's `EventSource` object reconnects automatically if the stream drops.

**Why buffering breaks it.** Any intermediary (proxy, CDN, API Gateway) that reads the full response before forwarding breaks the "never ends" property. The client sees a connection that hangs indefinitely, then receives the entire accumulated stream at once when the server finally closes. From the client's perspective, streaming silently degraded to batch.

**Three levers prevent buffering:**

1. **`Cache-Control: no-cache`** — tells caching layers not to buffer for cacheability checks.
2. **`X-Accel-Buffering: no`** — nginx/Cloud Run-specific opt-out. Named for nginx's `X-Accel` directive family.
3. **`: ping\n\n` every 15s** — SSE comment lines (starting with `:`). Clients ignore them; intermediaries see "still alive" and don't timeout the connection. Also pushes the TCP buffer out if the agent hasn't emitted a real event in a while.

## Minimal FastAPI SSE endpoint

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import asyncio, json

app = FastAPI()

async def event_stream(event_id: str):
    yield f"event: coordinator_start\ndata: {json.dumps({'event_id': event_id})}\n\n"
    # ... real work ...
    # ADK streaming integration: iterate over agent's stream()
    async for token in coordinator.stream(event_id):
        yield f"event: coordinator_thinking\ndata: {json.dumps({'text': token})}\n\n"
    yield f"event: done\ndata: {json.dumps({'status': 'complete'})}\n\n"

@app.get("/triage/stream")
async def triage_stream(event_id: str):
    return StreamingResponse(
        event_stream(event_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
```

FastAPI has an `EventSourceResponse` in newer versions (commit `22381558` adds keep-alive pings automatically every 15s). If available, prefer that; it handles the three headers for you.

## Project implications

1. **Sprint 4 owns this.** ADR-004 commits to hybrid SSE + Gemini text streaming at `/triage/stream`. Not a Sprint 0 concern, but Sprint 0 `middleware/` layer must not buffer — avoid any middleware that reads full response bodies (e.g., gzip at Cloud Run level).
2. **Deployment path: Cloud Run direct, not API Gateway.** Sprint 5 deploy guide should call this out. Cloud Run honors `X-Accel-Buffering: no`. API Gateway has its own documented buffering that these headers don't defeat.
3. **Non-streaming fallback is mandatory (ADR-004 §Alternatives).** If Sprint 4 streaming doesn't work by Day 1, wrap the stream consumer in a list-accumulator and return the full `TriageResult` as a single JSON response. The same event generator can feed both.
4. **Test with both `curl -N` and a real browser EventSource.** Some buffering issues only appear with specific client behaviors. Sprint 4 acceptance test must hold the stream open 30+ seconds and observe time-of-arrival per event.
5. **Cloud Run cold starts are a separate pitfall** — if the first request to `/triage/stream` triggers a cold start, the browser sees an 8-second silence. `min-instances=1` (~$5/month) hides this.

## The event schema (from Coordinator spec)

```
event: coordinator_start
data: {"event_id": "ev_001", "user_id": "u_123"}

event: coordinator_thinking
data: {"text": "streamed token chunk..."}

event: classification_ready
data: {full ClassificationResult JSON}

event: coordinator_thinking
data: {"text": "more streamed tokens..."}

event: impact_ready
data: {full ImpactResult JSON}

event: summary
data: {"text": "streamed summary tokens..."}

event: done
data: {full TriageResult JSON}
```

Event order is fixed. Consumer (browser) uses the named events to drive UI state transitions: show classifier spinner on `coordinator_start`, render classification card on `classification_ready`, etc.

## Gotchas flagged

- **CORS + SSE.** `EventSource` doesn't send preflight. Server-side CORS handling must include the `/triage/stream` path in allowlisted origins. Our CORS middleware (Sprint 0) already handles this; just verify Sprint 4 doesn't accidentally drop the `Access-Control-Allow-Origin` header for streaming responses.
- **Cloud Run response timeout is 60m max** but default 5m. Long-running triage could exceed; set explicit timeout per deployment.
- **HTTP/2 multiplexing can behave weirdly with SSE** over certain CDNs. Not a known Cloud Run issue today, but worth a test if we put Firebase Hosting in front.
- **Browser EventSource retry** is automatic on disconnect. If our server has a bug that drops connections mid-stream, browser silently retries. Log with `correlation_id` to catch patterns.

## Further research

- **ADK streaming API shape.** Does `agent.stream()` emit structured events or only raw tokens? Sprint 4 will need to map ADK's native stream to our SSE event schema — what's the mapping code?
- **SSE alternative: gRPC streaming + grpc-web.** Heavier but more typed. Only consider for Tier 3+ if SSE proves fragile.
- **Token-by-token vs chunk-by-chunk.** Gemini can emit tokens as they're generated. Browsers render at ~60fps; 1000 tokens/sec would overwhelm. Need a backpressure/batching strategy.
- **Reconnect semantics.** If browser reconnects, does the backend replay from event 1, or resume from where it left off? Implementing resume requires an `event_id` cursor — nice-to-have, probably Tier 3.

## Related decisions

- **ADR-004 Streaming strategy** — the SSE + Gemini hybrid this Zettel supports.
- **ADR-007 UI strategy** — React frontend (Sprint 5) consumes this stream via `EventSource`.
- **`.claude/rules/api-routes.md`** — project conventions for FastAPI route handlers.

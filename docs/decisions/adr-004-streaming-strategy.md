---
title: "ADR-004: Streaming Strategy — Hybrid SSE + Gemini Text Streaming"
type: deep-dive
domains: [supply-chain, api-design, streaming]
last_updated: 2026-04-10
status: active
confidence: medium
sources: ["[[Supply-Chain-Agent-Spec-Coordinator]]", "[[Supply-Chain-Sprint-Plan-Spiral-SDLC]]"]
---

# ADR-004: Streaming Strategy — Hybrid SSE + Gemini Text Streaming

## Status
Accepted

## Date
2026-04-10

## Context

The triage pipeline takes 2–6 seconds (Classifier → Impact → Coordinator synthesis). A cold UI with no feedback feels broken. The demo needs drama — judges should SEE the agents thinking.

Constraints:
- Cloud Run + FastAPI backend
- React frontend (Sprint 5) or `adk web` (Sprints 1–3, per ADR-007)
- Demo must feel responsive during judge review
- No WebSocket complexity for a solo builder
- Must degrade gracefully if streaming fails

Two streaming layers exist:
1. **Structural events** — "classifier started", "classifier done", "impact started", "done" — discrete milestones
2. **Token-by-token text** — the actual LLM generation as it happens, for coordinator thinking + final summary

## Decision

**Use hybrid SSE (Server-Sent Events) for structural events + Gemini native text streaming for token chunks**, delivered over a single SSE connection from the `/triage/stream` FastAPI endpoint.

Event schema (from [[Supply-Chain-Agent-Spec-Coordinator]]):

```
event: coordinator_start
data: {...}

event: coordinator_thinking      ← streamed Gemini tokens
data: {"text": "checking safety keywords..."}

event: classification_ready
data: {full ClassificationResult JSON}

event: coordinator_thinking
data: {"text": "escalating to Impact Agent..."}

event: impact_ready
data: {full ImpactResult JSON}

event: summary                   ← streamed Gemini tokens
data: {"text": "The NH-48 stoppage affects..."}

event: done
data: {full TriageResult JSON}
```

## Alternatives Considered

- **WebSocket bidirectional**: Rejected — overkill for one-way server→client streaming, adds complexity and Cloud Run sidecar config.
- **SSE-only, no text streaming**: Simple but loses demo drama. Rejected.
- **Gemini text streaming only, no structural events**: Confuses the UI — how does it know when a sub-agent finishes? Rejected.
- **Long polling**: Worst of both worlds — complexity of polling + latency of periodic fetches. Rejected.
- **Non-streaming JSON response**: **Explicit fallback.** If Sprint 4 streaming implementation runs over time, we ship a synchronous `/triage` endpoint returning full TriageResult JSON. Named Should-Have trim per sprint plan.

## Consequences

### Positive
- Best demo drama — judges see agents progress in real time
- Single HTTP connection, no special infrastructure
- Structural events give the UI precise handoff points
- Token streaming feels alive during coordinator reasoning
- Non-streaming fallback is trivially available (wrap stream consumer in a list-accumulator)

### Negative
- FastAPI SSE + ADK streaming integration is uncharted — risk of event buffering quirks
- Cloud Run response buffering may interfere with SSE (must set `Cache-Control: no-cache`, `X-Accel-Buffering: no`)
- Sprint 4 has one full day budgeted for this; bleed risk is real
- Frontend (Sprint 5) must implement `EventSource` or similar — React team needs clear docs

### Neutral
- Sprint 4 PRD must include a Day 1 go/no-go: if SSE+Gemini hybrid isn't working by end of Day 1, fall back to non-streaming JSON for the demo
- `api_endpoint.py` uses `fastapi.responses.StreamingResponse` with `media_type="text/event-stream"`
- Integration test in Sprint 4: SSE event ordering + error recovery

## References

- [FastAPI Server-Sent Events docs](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse)
- [Gemini API streaming docs](https://ai.google.dev/gemini-api/docs/text-generation#streaming)
- [MDN Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
- [Cloud Run Streaming Responses](https://cloud.google.com/run/docs/triggering/https-request#response-streaming)
- [[Supply-Chain-Agent-Spec-Coordinator]] §"Streaming Event Schema (SSE)" — canonical event list
- [[Supply-Chain-Sprint-Plan-Spiral-SDLC]] — Sprint 4 budget and Should-Have trim rules

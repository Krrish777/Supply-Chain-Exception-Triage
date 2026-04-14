---
description: OpenTelemetry spans, structured logging, cost attribution, PII redaction
paths: ["src/**"]
---

# Observability rules

Every agent invocation, tool call, and LLM request emits a span with token usage. If you can't attribute cost to an agent, you can't optimize it.

## 1. OpenTelemetry spans

**Per agent invocation + per tool call**, span attributes (minimum):
- `agent.name`
- `agent.model` (e.g. `gemini-2.5-flash`)
- `gen_ai.request.model`
- `gen_ai.usage.input_tokens`
- `gen_ai.usage.output_tokens`
- `exception.id` (where relevant)

Follow OTel GenAI semantic conventions: https://opentelemetry.io/docs/specs/semconv/gen-ai/

## 2. Exporter + instrumentation

- Exporter: `opentelemetry-exporter-gcp-trace`.
- FastAPI: `opentelemetry-instrumentation-fastapi`.
- ADK emits its own spans — propagate `traceparent` across sub-agent calls via context (do not create fresh tracers per request).

## 3. Span processor shutdown

Shut down the span processor on SIGTERM, otherwise Cloud Run loses final traces on scale-down:

```python
import signal
from opentelemetry.sdk.trace import TracerProvider

def _shutdown(*_):
    tracer_provider.shutdown()

signal.signal(signal.SIGTERM, _shutdown)
```

## 4. Structured JSON logs (stdout)

Cloud Run auto-correlates logs with traces when logs contain:
- `severity`
- `message`
- `logging.googleapis.com/trace`
- `logging.googleapis.com/spanId`

Use `structlog` (already in deps) + a JSON renderer. **Never** `print()`.

## 5. PII + prompt redaction

**Never** log full Gemini prompts / responses — PII leak and log cost. At a middleware boundary:
- Allowlist fields that can be logged.
- Hash or redact identifiers like shipment IDs, customer names, emails.
- Body redaction happens BEFORE the log record is formatted, not after.

## 6. Cost attribution

Every Gemini response carries `usage_metadata`. Write it to a span attribute AND a log-based metric keyed by `agent.name`:

```python
span.set_attribute("gen_ai.usage.input_tokens", resp.usage_metadata.prompt_token_count)
span.set_attribute("gen_ai.usage.output_tokens", resp.usage_metadata.candidates_token_count)
```

Budget alerts per GCP project at 50/90/100%. Dashboard: token burn per agent per day.

## 7. Firestore op counting

Wrap reads/writes in a thin helper in `memory/` that increments a counter. Surfaces the "which agent is causing the N+1" question before the bill does.

## 8. Log retention

- Dev: 30 days.
- Staging: 30 days.
- Prod: 90 days.

Set via log bucket configuration, not application code.

## 9. Anti-patterns

- `print()` statements.
- Fresh tracer per request.
- Logging prompts verbatim.
- No per-agent cost attribution.
- Retry logic without tracing the retries (can't tell loops from single requests).
- Reading Secret Manager / OTel config at module import (cold-start latency).

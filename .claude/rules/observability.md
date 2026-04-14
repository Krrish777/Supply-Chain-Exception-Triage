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

## 6. `audit_event` helper contract

The audit log is a **typed, event-keyed subset** of structured logging. Callers never touch `structlog` directly for audit events — they call `audit_event(event, **kwargs)`.

### Signature

```python
# src/supply_chain_triage/middleware/audit_log.py
def audit_event(event: str, *, correlation_id: str, user_id: str, company_id: str, **kwargs) -> None:
    """Emit an audit event to structured logs.

    Required kwargs (enforced — ValueError if any is missing or empty):
        correlation_id: request / invocation correlation UUID
        user_id:        Firebase uid (or "system" for scheduled jobs)
        company_id:     tenant ID from custom claims (or "system")
    """
```

- **Module-level function**, NOT a class instance. Usable outside HTTP middleware context (batch jobs, ADK callbacks, scheduled tasks).
- Emits via the same `structlog` chain as §4 / §5 — the PII-drop processor still applies.
- Raises `ValueError` if any required key is missing or empty — catches silent drift where someone forgets to pass `company_id`.

### Canonical event names

Use these exact strings (grep-able across the codebase):

| Event | When |
|---|---|
| `auth_login` | Successful Firebase ID-token verification |
| `auth_failure` | Failed verification (expired, revoked, invalid) |
| `permission_denied` | Tier / tenant authorization rejected |
| `rate_limit_hit` | slowapi returned 429 |
| `agent_invoked` | `Runner.run_async` entry |
| `agent_completed` | `Runner.run_async` exit — include `status`, `latency_ms` |
| `tool_invoked` | Tool function called — include `tool_name`, `status` |
| `classification_result` | Classifier returned — include `category`, `severity`, `confidence` |
| `escalation_triggered` | `requires_human=True` was set — include `failure_reason` |
| `secret_rotated` | Secret Manager revision change observed |

New event types require an entry in this table + a code-review mention.

### Loggable vs not

**Loggable** (in `**kwargs`): `correlation_id` (required), `user_id` (required), `company_id` (required), `agent_name`, `tool_name`, `exception_id` (ULID), `latency_ms`, `status`, `category`, `severity`, `confidence`, `http_status`, `failure_reason` (one-line error classification), `source_ip` (if needed for abuse tracking).

**Never passed to `audit_event`:** raw Gemini prompts, Gemini output, Firestore doc contents, emails, phone numbers, free-text user input — the PII-drop processor is the backstop, but callers should not pass these keys in the first place.

### Example

```python
from supply_chain_triage.middleware.audit_log import audit_event

audit_event(
    "classification_result",
    correlation_id=request_id,
    user_id=current_user.uid,
    company_id=current_user.tenant_id,
    agent_name="classifier",
    category="carrier_capacity_failure",
    severity="CRITICAL",
    confidence=0.92,
    latency_ms=842,
)
```

### Placement

- `src/supply_chain_triage/middleware/audit_log.py` — helper function + `AuditLogMiddleware` (the ASGI layer that auto-emits `http_request` / `http_response` pairs).
- Call sites live anywhere (agents, tools, routes, scheduled jobs, ADK callbacks).
- `audit_event` has **no ADK or Firestore imports** — passes the import rules in `.claude/rules/imports.md` so tools and utils can call it freely.

### Relation to §5 PII redaction

`audit_event` is a **typed wrapper** over `structlog.get_logger().info(event, **kwargs)` with required-key enforcement. The PII-drop processor chain from §5 is still in force as defence-in-depth. The typed wrapper's job is catching **forgotten required keys** and standardizing event names; the processor's job is catching **banned content**.

## 7. Cost attribution

Every Gemini response carries `usage_metadata`. Write it to a span attribute AND a log-based metric keyed by `agent.name`:

```python
span.set_attribute("gen_ai.usage.input_tokens", resp.usage_metadata.prompt_token_count)
span.set_attribute("gen_ai.usage.output_tokens", resp.usage_metadata.candidates_token_count)
```

Budget alerts per GCP project at 50/90/100%. Dashboard: token burn per agent per day.

## 8. Firestore op counting

Wrap reads/writes in a thin helper in `memory/` that increments a counter. Surfaces the "which agent is causing the N+1" question before the bill does.

## 9. Log retention

- Dev: 30 days.
- Staging: 30 days.
- Prod: 90 days.

Set via log bucket configuration, not application code.

## 10. Anti-patterns

- `print()` statements.
- Fresh tracer per request.
- Logging prompts verbatim.
- No per-agent cost attribution.
- Retry logic without tracing the retries (can't tell loops from single requests).
- Reading Secret Manager / OTel config at module import (cold-start latency).
- Calling `structlog.get_logger().info(event_name, ...)` directly for auditable events — use `audit_event()` so required keys are enforced.
- Inventing new audit event names inline — add to the canonical table in §6 first.
- Passing raw prompt / response strings to `audit_event` — the PII-drop processor catches them, but the call site is wrong.

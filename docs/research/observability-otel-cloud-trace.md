---
title: "Observability: OpenTelemetry + Cloud Trace + Cloud Logging for Supply-Chain Triage (Tier 1)"
slug: observability-otel-cloud-trace
status: research
audience: [engineering, hackathon-judge-prep]
tier: 1
decision_date: 2026-04-18
owners: [Krrish]
related:
  - .claude/rules/observability.md
  - .claude/rules/logging.md
  - src/supply_chain_triage/utils/logging.py
  - src/supply_chain_triage/middleware/audit_log.py
  - docs/research/Architecture-Decision-Analysis-summary.md
scope:
  tier_1_in:
    - OpenTelemetry Python SDK in the FastAPI lifespan
    - opentelemetry-exporter-gcp-trace -> Cloud Trace
    - Per-agent + per-tool spans with GenAI semantic conventions
    - structlog JSON on stdout -> Cloud Logging (auto-correlated via magic fields)
    - Per-agent cost attribution via gen_ai.usage.* attributes
    - $10 / $25 / $50 budget alerts
    - SIGTERM flush guard on Cloud Run
  tier_1_out:
    - BigQuery log sink (deferred; Cloud Logging retention sufficient for demo)
    - Grafana / external trace backend
    - Distributed tracing across A2A hops (Tier 3)
    - OTel metrics pipeline (Cloud Monitoring via log-based metrics only for Tier 1)
gcp_region: asia-south1
---

# Observability — OpenTelemetry + Cloud Trace + Cloud Logging (Tier 1)

> **One-liner:** Every agent and tool emits an OTel span with GenAI semantic-convention
> attributes; spans go to Cloud Trace via the GCP exporter; structlog emits JSON on
> stdout with the three magic trace-correlation fields so Cloud Run auto-links logs
> to the trace waterfall. Cost attribution comes free because each `LlmResponse`
> carries `usage_metadata` that we write straight to `gen_ai.usage.input_tokens` /
> `gen_ai.usage.output_tokens` on the current span. The demo artifact is a single
> Cloud Trace waterfall showing Classifier -> Impact with per-span token counts.

---

## 1. Executive summary

Tier 1 observability has a tight deadline (2026-04-24 ship date, demo day shortly
after) and one hard deliverable: a judge must see **where an NH-48 test run spent
its milliseconds and tokens**. That rules in Cloud Trace (visual waterfall) and
Cloud Logging (per-request timeline with PII scrubbed). It rules out anything
that needs a separate backend, a heavyweight collector, or a React frontend.

Decision:

| Concern | Tier 1 choice | Why |
|---|---|---|
| Trace backend | **Cloud Trace** | Free up to the 2.5M spans/month tier; native GCP; auto-links to Logs. |
| Log backend | **Cloud Logging** | Cloud Run writes stdout straight there; three magic fields link to Cloud Trace. |
| Metrics | **Log-based metrics** | No OTel metrics pipeline required for Tier 1; counter/histogram derived from structured log events. |
| BigQuery sink | **Deferred** | Cloud Logging's 30-day retention is enough for the demo; BQ sink is a Tier 2 follow-up. |
| Budget | **$10 / $25 / $50 email alerts** | Three-step pager so a runaway loop is noticed before the real cap. |
| SIGTERM flush | **Mandatory** | Without it, Cloud Run scale-down drops the last span in a trace; the demo will silently lose the tail. |

The code surface is small: one new module (`core/tracing.py`), a few lines each
in `main.py`, `classifier/agent.py`, `impact/agent.py`, and the existing
`utils/logging.py` and `middleware/audit_log.py` files. No new processes, no
sidecars, no collector deploy.

---

## 2. Package list (add to `pyproject.toml`)

All six are Python 3.13 compatible as of this session (April 2026). Add to the
main `dependencies` block alongside `structlog`:

```toml
# --- Observability (Tier 1) ---
"opentelemetry-api>=1.27.0",
"opentelemetry-sdk>=1.27.0",
"opentelemetry-exporter-gcp-trace>=1.9.0",       # CloudTraceSpanExporter
"opentelemetry-instrumentation-fastapi>=0.48b0", # ASGI middleware
"opentelemetry-semconv>=0.48b0",                 # semconv constant strings
"opentelemetry-resourcedetector-gcp>=1.9.0",     # Cloud Run / GCE resource detection
```

Two deliberately **not** pulled in:

- `opentelemetry-instrumentation-google-genai` — ADK >=1.17 already emits
  `call_llm` spans for Gemini calls; pulling in this instrumentor double-counts.
  Re-evaluate at Tier 2 when we may bypass ADK for Judge calls.
- `opentelemetry-exporter-gcp-logging` — Cloud Run's built-in log agent already
  parses JSON on stdout; adding an OTLP logs exporter adds a round-trip with no
  benefit for Tier 1. Reconsider at Tier 3 if we need OTel-native log bodies.

**uv install:**

```bash
uv add opentelemetry-api opentelemetry-sdk opentelemetry-exporter-gcp-trace \
       opentelemetry-instrumentation-fastapi opentelemetry-semconv \
       opentelemetry-resourcedetector-gcp
uv sync --locked   # keeps uv.lock in sync — CI drift gate will check
```

Lock is committed per project convention.

---

## 3. Initialization inside FastAPI `lifespan`

File: new `src/supply_chain_triage/core/tracing.py`. The lifespan hook in
`runners/` (or `main.py` for now) calls `configure_tracing()` once per process.

```python
"""OpenTelemetry bootstrap — one tracer provider per process.

Called from the FastAPI lifespan (never at module import — violates the rule in
.claude/rules/security.md §6). Registers Cloud Trace exporter, FastAPI
instrumentation, and a SIGTERM handler that flushes spans before Cloud Run
reaps the instance.
"""
from __future__ import annotations

import os
import signal
from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.resourcedetector.gcp_resource_detector import (
    GoogleCloudResourceDetector,
)
from opentelemetry.sdk.resources import Resource, get_aggregated_resources
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

if TYPE_CHECKING:
    from fastapi import FastAPI

_SERVICE_NAME = "sct-triage"
_tracer_provider: TracerProvider | None = None


def configure_tracing(app: "FastAPI") -> TracerProvider:
    """Install the global tracer provider + FastAPI instrumentation.

    Safe to call once per process. Second call is a no-op (returns existing).
    """
    global _tracer_provider  # noqa: PLW0603 — one-shot bootstrap is the point
    if _tracer_provider is not None:
        return _tracer_provider

    # Resource detection — Cloud Run fills service.instance.id, cloud.region,
    # cloud.resource_id automatically when running on Cloud Run.
    resource = get_aggregated_resources(
        [GoogleCloudResourceDetector(raise_on_error=False)],
        initial_resource=Resource.create(
            {
                "service.name": _SERVICE_NAME,
                "service.version": os.getenv("SERVICE_VERSION", "0.1.0"),
                "service.instance.id": os.getenv("K_REVISION", "local"),
                "deployment.environment": os.getenv("ENV", "dev"),
            },
        ),
    )

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(
            CloudTraceSpanExporter(),
            # Tight queues keep the SIGTERM-flush window small (Cloud Run
            # gives 10s). Defaults (2048 queue, 512 batch) can overflow the
            # 10s budget on a cold scale-down.
            max_queue_size=512,
            max_export_batch_size=128,
            schedule_delay_millis=2000,
            export_timeout_millis=5000,
        ),
    )
    trace.set_tracer_provider(provider)

    # Propagator — W3C traceparent is what ADK + FastAPI both use.
    set_global_textmap(
        CompositePropagator([TraceContextTextMapPropagator()]),
    )

    # FastAPI ASGI instrumentation — every HTTP request becomes the root span.
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)

    _install_sigterm_flush(provider)

    _tracer_provider = provider
    return provider


def _install_sigterm_flush(provider: TracerProvider) -> None:
    """Cloud Run sends SIGTERM 10s before SIGKILL. Flush before then."""
    def _shutdown(*_: object) -> None:
        # provider.shutdown() calls force_flush() + shuts down each processor.
        # Safe to call multiple times; internal _shutdown_called flag gates.
        provider.shutdown()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)  # local dev Ctrl+C
```

Wire into `src/supply_chain_triage/main.py`:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from supply_chain_triage.core.tracing import configure_tracing

@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_tracing(app)
    # ... Firestore AsyncClient, Secret Manager reads, etc.
    yield
    # Shutdown handled by signal handler; nothing to do here.

def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan, title="Supply Chain Exception Triage")
    # middleware stack (unchanged) ...
    return app
```

**Import layer note:** `core/tracing.py` imports `opentelemetry.*`. Per
`.claude/rules/architecture-layers.md` §2, `core/` is allowed to import external
deps (it's the DI chokepoint). `opentelemetry-*` is neither `google.adk` nor
`firebase_admin` / `google.cloud.firestore`, so the `TID251` banned-api rules
don't touch it. No `per-file-ignores` entry needed.

---

## 4. Per-agent span wiring (ADK callbacks)

ADK >=1.17 ships its own `call_llm` span around each Gemini call. Good — we
don't reinvent that. What we **add** is a surrounding `agent.<name>` span that
covers fetcher + formatter + post-processing, plus a `tool.<name>` child span
per tool call. The ADK `call_llm` span becomes a child of `agent.<name>`
automatically because they share the same trace context.

### 4.1 Helper module

File: extend `src/supply_chain_triage/core/tracing.py` with span helpers so
agent modules don't import `opentelemetry.*` directly (keeps the blast radius
of a future framework swap small):

```python
from opentelemetry import trace as _trace
from opentelemetry.trace import Span, Status, StatusCode

_tracer = _trace.get_tracer("sct.agents")


def start_agent_span(name: str, model: str) -> Span:
    """Start a span named `agent.<name>` with GenAI semconv attributes.

    Returned span is NOT set as current — the caller must `use_span` or set
    it via context. ADK callbacks run on the event loop; a span started in
    `before_agent_callback` and ended in `after_agent_callback` wraps the
    whole sub-agent sequence, so we store the span on `callback_context.state`
    under the `temp:` prefix (session state, not persisted).
    """
    span = _tracer.start_span(f"agent.{name}")
    span.set_attribute("agent.name", name)
    span.set_attribute("agent.model", model)
    span.set_attribute("gen_ai.provider.name", "gcp.gemini")
    span.set_attribute("gen_ai.operation.name", "chat")
    span.set_attribute("gen_ai.request.model", model)
    return span


def end_agent_span(
    span: Span,
    *,
    tokens_in: int,
    tokens_out: int,
    duration_ms: float,
    error: str | None = None,
) -> None:
    """Close an agent span with token usage + duration attributes."""
    span.set_attribute("gen_ai.usage.input_tokens", tokens_in)
    span.set_attribute("gen_ai.usage.output_tokens", tokens_out)
    span.set_attribute("duration_ms", duration_ms)
    if error:
        span.set_status(Status(StatusCode.ERROR, error))
        span.set_attribute("error.type", error)
    else:
        span.set_status(Status(StatusCode.OK))
    span.end()


def start_tool_span(tool_name: str, agent_name: str) -> Span:
    span = _tracer.start_span(f"tool.{tool_name}")
    span.set_attribute("tool.name", tool_name)
    span.set_attribute("agent.name", agent_name)
    return span


def end_tool_span(span: Span, *, status: str, error: str | None = None) -> None:
    span.set_attribute("tool.status", status)
    if error:
        span.set_status(Status(StatusCode.ERROR, error))
        span.set_attribute("error.type", error)
    span.end()
```

### 4.2 Classifier callbacks (minimal diff)

The existing `_before_agent` / `_after_model` / `_after_agent` callbacks in
`src/supply_chain_triage/modules/triage/agents/classifier/agent.py` already
track start time + token accumulation via `callback_context.state`. We reuse
that state and just add span bookkeeping:

```python
# At the top — new imports.
from supply_chain_triage.core.tracing import (
    end_agent_span,
    end_tool_span,
    start_agent_span,
    start_tool_span,
)

_STATE_SPAN = f"temp:{_AGENT_NAME}:span"  # OTel Span object — temp-scoped.


def _before_agent(callback_context: CallbackContext) -> None:
    """Stamp start time + open an agent span."""
    callback_context.state[_STATE_START] = time.perf_counter_ns()
    callback_context.state[_STATE_SPAN] = start_agent_span(
        name=_AGENT_NAME, model=_MODEL_NAME,
    )


def _after_agent(callback_context: CallbackContext) -> None:
    """Post-processing + close the agent span."""
    start_ns = callback_context.state.get(_STATE_START)
    duration_ms = (time.perf_counter_ns() - start_ns) / 1_000_000 if start_ns else 0.0

    raw_classification = callback_context.state.get("triage:classification")
    if raw_classification and isinstance(raw_classification, str):
        _apply_post_classification_rules(callback_context, raw_classification)

    tokens_in = callback_context.state.get(_STATE_TOKENS_IN, 0)
    tokens_out = callback_context.state.get(_STATE_TOKENS_OUT, 0)

    log_agent_invocation(
        agent_name=_AGENT_NAME,
        duration_ms=duration_ms,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        model=_MODEL_NAME,
    )

    span = callback_context.state.pop(_STATE_SPAN, None)
    if span is not None:
        end_agent_span(
            span,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            duration_ms=duration_ms,
        )
```

**Note on `temp:` prefix** — per `.claude/rules/agents.md` §2, `temp:` keys
never persist to `SessionService`. An OTel `Span` object is not
JSON-serializable, so this is mandatory, not optional. If we drop this
prefix, ADK's state delta serializer will raise.

**Why `_before_agent` on the `SequentialAgent`, not the sub-agents:** the two
sub-agents (fetcher + formatter) each produce their own `call_llm` span via
ADK. By opening `agent.classifier` at the SequentialAgent level and closing it
in `after_agent_callback`, the ADK spans end up as children, and the waterfall
shows the full composition. If we opened the span on the fetcher alone, the
formatter's LLM call would be a sibling trace, not nested.

### 4.3 Tool spans via `before_tool_callback` / `after_tool_callback`

Currently neither the Classifier nor the Impact agent defines tool callbacks.
Add them at the fetcher level (fetcher is the only sub-agent with tools —
formatter has `include_contents="none"`):

```python
def _before_tool(
    tool: Any,                    # google.adk.tools.BaseTool
    args: dict[str, Any],         # noqa: ARG001
    tool_context: Any,            # google.adk.tools.ToolContext
) -> None:
    """Open a tool span keyed by tool.name."""
    span = start_tool_span(tool_name=tool.name, agent_name=_AGENT_NAME)
    tool_context.state[f"temp:{_AGENT_NAME}:tool_span:{tool.name}"] = span


def _after_tool(
    tool: Any,
    args: dict[str, Any],         # noqa: ARG001
    tool_context: Any,
    tool_response: dict[str, Any],
) -> None:
    """Close the matching tool span."""
    key = f"temp:{_AGENT_NAME}:tool_span:{tool.name}"
    span = tool_context.state.pop(key, None)
    if span is None:
        return
    status = tool_response.get("status", "unknown")
    err = tool_response.get("error_message") if status != "success" else None
    end_tool_span(span, status=status, error=err)
```

Wire into the fetcher `LlmAgent(...)` call:

```python
fetcher = LlmAgent(
    name="classifier_fetcher",
    # ...
    before_tool_callback=_before_tool,
    after_tool_callback=_after_tool,
    after_model_callback=_after_model,
)
```

### 4.4 Same pattern for Impact agent

Identical surgery in `modules/triage/agents/impact/agent.py`:

- Import the four `start_/end_` helpers.
- Add `_STATE_SPAN` key, open in `_before_agent`, close in `_after_agent`.
- Add `_before_tool` / `_after_tool` callbacks on the `impact_fetcher`
  (it has six tools; same state-key pattern scales).

### 4.5 What the final trace looks like

For one `/triage` request on exception NH-48:

```
POST /triage/submit                              (FastAPI — root)
  +- agent.classifier                            (SequentialAgent)
  |    +- call_llm (classifier_fetcher)          (ADK built-in)
  |    |    +- tool.get_exception_event          (our tool span)
  |    |    +- tool.get_company_profile
  |    +- call_llm (classifier_formatter)
  +- agent.impact
       +- call_llm (impact_fetcher)
       |    +- tool.get_exception_event
       |    +- tool.get_affected_shipments
       |    +- tool.calculate_financial_impact
       +- call_llm (impact_formatter)
```

Every span carries `gen_ai.request.model=gemini-2.5-flash` plus the relevant
token counts. Clicking into any span in the Cloud Trace UI reveals the linked
log entries (§7 below explains why).

---

## 5. GenAI semantic conventions — compliance table

Tier 1 emits these attributes. Spec status as of April 2026: **Development**
(not marked stable). `stable_status` column reflects what the OTel spec
promises about backward compatibility.

| Attribute | Set where | Value | Required level | Spec URL |
|---|---|---|---|---|
| `gen_ai.system` | agent span | `"gcp.gemini"` (deprecated alias for `gen_ai.provider.name`) | Opt-in (deprecated; we set `provider.name` instead) | [gen-ai/](https://opentelemetry.io/docs/specs/semconv/gen-ai/) |
| `gen_ai.provider.name` | agent span | `"gcp.gemini"` | **Required** | [gen-ai-spans/](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/) |
| `gen_ai.operation.name` | agent span | `"chat"` | **Required** | same |
| `gen_ai.request.model` | agent span | `"gemini-2.5-flash"` | Conditionally required | same |
| `gen_ai.response.model` | after `call_llm` (ADK sets) | echoed from response | Conditionally required | same |
| `gen_ai.response.id` | after `call_llm` (ADK sets) | Gemini completion ID | Recommended | same |
| `gen_ai.usage.input_tokens` | `after_agent_callback` | sum of both sub-agents' prompts | **Recommended** | [registry/attributes/gen-ai/](https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/) |
| `gen_ai.usage.output_tokens` | `after_agent_callback` | sum of both sub-agents' candidates | **Recommended** | same |
| `error.type` | on failure | short classifier string | Conditionally required | same |
| `agent.name` | agent + tool spans | `"classifier"` / `"impact"` | project-local | — |
| `agent.model` | agent span | `"gemini-2.5-flash"` | project-local | — |
| `tool.name` | tool span | `"get_exception_event"` etc. | project-local | — |
| `tool.status` | tool span | `"success"` / `"error"` / `"retry"` | project-local | — |
| `duration_ms` | agent span | float milliseconds | project-local | — |
| `exception.id` | agent span (when known) | ULID of the exception under triage | project-local | — |

**`gen_ai.system` vs `gen_ai.provider.name`:** the spec is mid-migration. As
of April 2026 `gen_ai.provider.name` is the required one; `gen_ai.system` is
kept as a deprecated alias for one more release. Set the new name only.

**Opt-in attributes we deliberately skip:**

- `gen_ai.input.messages` — raw prompt text. Huge PII leak, huge span size.
- `gen_ai.output.messages` — raw response text. Same issue. If a judge asks
  "where's the response body," the answer is "Firestore, keyed by
  `exception.id` + `triage_results/{resultId}` — never the span."
- `gen_ai.system_instructions` — system prompt. Our prompts are in the repo;
  no value in paying for the span size.

Explicit env var to lock this in: `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=false`
(read by the optional `opentelemetry-instrumentation-google-genai` if it ever
gets pulled in for a downstream agent).

---

## 6. Cost attribution end-to-end

```
 Gemini call
      |
      |  LlmResponse.usage_metadata.prompt_token_count
      |                             .candidates_token_count
      v
 _after_model callback                (classifier/agent.py + impact/agent.py)
      |  accumulates into callback_context.state["temp:<agent>:tokens_(in|out)"]
      v
 _after_agent callback
      |  end_agent_span(span, tokens_in=..., tokens_out=...)
      |  also log_agent_invocation(...)  (structured log event)
      v
 +----+----------------------+
 |                           |
 v                           v
 Cloud Trace span          Cloud Logging entry
  gen_ai.usage.input_tokens   jsonPayload.tokens_in
  gen_ai.usage.output_tokens  jsonPayload.tokens_out
  agent.name                  jsonPayload.agent_name
      |                             |
      v                             v
 (visual: trace waterfall)  (query: log-based metric — sum over agent_name)
                                    |
                                    v
                       Cloud Monitoring custom metric
                         logging.googleapis.com/user/sct_tokens_in
                         logging.googleapis.com/user/sct_tokens_out
                                    |
                                    v
                       Dashboard: token burn per agent per hour
                                    |
                                    v
                       Budget alert at $10 / $25 / $50
                       (Gemini 2.5 Flash Tier 1 bill)
```

The pipeline has **two recording paths** for the same number. That's deliberate:

- **Trace attribute** — debug lens. Select one trace, see the token count on
  the span. Fast answer to "did this one request blow up?"
- **Log entry** — aggregate lens. MQL / log-based metric sums over time.
  Answers "which agent is costing us the most this hour?"

Single-source would be neater but each path serves a different question, and
both are cheap (one span attribute, one log field).

**Gemini `usage_metadata` quirks** (verified in existing
`_after_model` callback):

- `prompt_token_count` — includes thinking tokens on 2.5 Flash when
  `thinking_config` is set. Our agents use `thinking_budget=1024`, so
  input tokens > the fetcher instruction length alone.
- `candidates_token_count` — just the visible response, does not include
  thinking. Matches what the user sees.
- Both can be `None` on tool-only turns (no LLM response); our callback
  guards with `... or 0`.

---

## 7. Logging — structlog + GCP JSON renderer

The existing `utils/logging.py` is 90% there. It already:

- Configures a structlog processor chain with PII drop + JSON renderer.
- Emits JSON to stdout when `LOG_TO_FILES=0` (the Cloud Run path).
- Binds a `request_id` via `structlog.contextvars`.

What's missing for log-to-trace correlation: the three magic Cloud Run fields.
Cloud Run's log agent parses stdout JSON; when it sees any of these top-level
keys, it extracts them into the `LogEntry` structure and the Logs Explorer
links the entry to the matching trace:

| JSON field | Becomes | Required format |
|---|---|---|
| `logging.googleapis.com/trace` | `LogEntry.trace` | `projects/<project>/traces/<32-hex-trace-id>` |
| `logging.googleapis.com/spanId` | `LogEntry.spanId` | 16-hex span ID |
| `logging.googleapis.com/trace_sampled` | `LogEntry.traceSampled` | boolean |
| `severity` | `LogEntry.severity` | `DEBUG`/`INFO`/`WARNING`/`ERROR` |
| `message` | `LogEntry.textPayload` (if JSON has `message` key) | string |

### 7.1 New structlog processor

Add to `utils/logging.py` — this processor reads the current OTel span and
emits the three magic fields. Place it **after** `merge_contextvars` so it
sees `request_id`, but **before** `_drop_pii` so PII-drop still runs on the
final dict.

```python
# --- in utils/logging.py, alongside _drop_pii ------------------------------

def _add_trace_context(
    _logger: Any,
    _method: str,
    event_dict: "MutableMapping[str, Any]",
) -> "MutableMapping[str, Any]":
    """Attach Cloud Run's magic trace/span/sampled fields to the event dict.

    Reads the current OTel span; no-ops if no span is active. Keeps this file
    the only place OTel is imported at the logging layer — avoids fanning
    out OTel imports across every call site. See .claude/rules/
    architecture-layers.md §2 — the `utils/logging.py` narrow exception.
    """
    try:
        from opentelemetry import trace as _otel_trace
    except ImportError:  # OTel optional on older local tooling — swallow.
        return event_dict

    span = _otel_trace.get_current_span()
    ctx = span.get_span_context()
    if not ctx.is_valid:
        return event_dict

    project_id = os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
    trace_id_hex = format(ctx.trace_id, "032x")
    span_id_hex = format(ctx.span_id, "016x")
    if project_id:
        event_dict["logging.googleapis.com/trace"] = (
            f"projects/{project_id}/traces/{trace_id_hex}"
        )
    event_dict["logging.googleapis.com/spanId"] = span_id_hex
    event_dict["logging.googleapis.com/trace_sampled"] = bool(ctx.trace_flags & 1)
    return event_dict
```

### 7.2 Also map structlog `level` to Cloud Run `severity`

Cloud Run accepts either uppercase `severity` or a numeric integer, but
structlog's `add_log_level` emits lowercase `level`. Add a one-liner rename
processor:

```python
def _rename_level_to_severity(
    _logger: Any,
    _method: str,
    event_dict: "MutableMapping[str, Any]",
) -> "MutableMapping[str, Any]":
    lvl = event_dict.pop("level", None)
    if lvl is not None:
        event_dict["severity"] = lvl.upper()
    return event_dict
```

### 7.3 Updated processor chain

Order matters — PII drop runs late so it catches anything earlier processors
added:

```python
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,   # request_id + bound vars
        _add_request_id,                           # stdlib fallback
        _add_trace_context,                        # NEW — Cloud Run magic fields
        structlog.processors.add_log_level,        # adds "level"
        _rename_level_to_severity,                 # NEW — level -> severity
        _drop_pii,                                 # drops banned keys
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)
```

### 7.4 Final event shape on stdout

What Cloud Run sees for an `agent_invoked` event:

```json
{
  "event": "agent_invoked",
  "agent_name": "classifier",
  "duration_ms": 842.1,
  "tokens_in": 1284,
  "tokens_out": 97,
  "model": "gemini-2.5-flash",
  "request_id": "a1b2c3d4e5f6",
  "correlation_id": "a1b2c3d4e5f6",
  "severity": "INFO",
  "timestamp": "2026-04-18T09:12:44.003Z",
  "logging.googleapis.com/trace": "projects/sct-prod/traces/8a1b9f0e3c4d5a6b7c8d9e0f1a2b3c4d",
  "logging.googleapis.com/spanId": "5a6b7c8d9e0f1a2b",
  "logging.googleapis.com/trace_sampled": true
}
```

Cloud Run's log agent turns the three magic fields into `LogEntry.trace`,
`LogEntry.spanId`, `LogEntry.traceSampled`. Cloud Console renders a
"View trace" link on every log row, and a "View logs" link on every trace
span. That's the whole correlation story — no extra SDK needed.

---

## 8. `audit_event` wiring — confirmation + follow-up

The existing helper at `src/supply_chain_triage/middleware/audit_log.py` is:

```python
def audit_event(event: str, **kwargs: Any) -> None:
    """Emit a structured audit event through the canonical logger."""
    _logger.info(event, **kwargs)
```

**Status per `.claude/rules/observability.md` §6:**

| Required-key enforcement | Canonical event names | Trace-context binding |
|---|---|---|
| NOT enforced (no ValueError on missing) | Partial — `request.start`/`.end`/`.error` only | Automatic, via §7 processor |

### 8.1 Trace-context binding — automatic, zero changes

Because `audit_event` funnels through the same `_logger.info(...)` path as
every other log call, the `_add_trace_context` processor (§7.1) fires on
every audit event. No changes needed in `audit_log.py` for trace correlation.

### 8.2 Required-key enforcement — gap vs the rule

`.claude/rules/observability.md` §6 specifies:

```python
def audit_event(event, *, correlation_id, user_id, company_id, **kwargs): ...
# Raises ValueError if any required key is missing or empty.
```

The current implementation uses `**kwargs` alone — required keys are not
enforced. This is a pre-Tier-1 follow-up (tracked in the task list at §16).
The drift it catches (someone forgets to pass `company_id` from a new ADK
callback) is real but hasn't bitten yet.

### 8.3 Canonical event emission — where each event should fire

Per observability rule §6:

| Event | Emit location | Status |
|---|---|---|
| `auth_login` | `FirebaseAuthMiddleware` on success | To-do — add after §16 task 3 |
| `auth_failure` | `FirebaseAuthMiddleware` on `Invalid/Expired/RevokedIdTokenError` | To-do |
| `permission_denied` | `require_tier(...)` dep on 403 raise | To-do |
| `rate_limit_hit` | slowapi handler on 429 | To-do (slowapi not yet added) |
| `agent_invoked` | `_before_agent` in each agent | **Done** (via `log_agent_invocation` — name drift: emits `agent_invoked`, not `agent_invoked` via `audit_event` specifically) |
| `agent_completed` | `_after_agent` (same log event) | **Done — but using the name `agent_invoked`**; should be split into `agent_invoked` on entry + `agent_completed` on exit with `latency_ms` + `status`. Tracked in §16. |
| `tool_invoked` | `_after_tool` callback | To-do — `log_tool_call` helper exists, not yet wired from agents |
| `classification_result` | `_after_agent` in classifier after post-rules | To-do — the data is there, just emit an extra `audit_event` |
| `escalation_triggered` | `_apply_post_classification_rules` on `requires_human_approval=True` | To-do |
| `secret_rotated` | Secret Manager revision change handler | To-do (no handler yet; lifespan logs current version) |

Concrete drift to fix now vs land later:

- **Now (pre-demo):** add `classification_result` in `_after_agent` — the
  judge-facing demo benefits from seeing the structured audit event in logs.
- **Later (Sprint 2):** harden `audit_event` signature with required-key
  validation; wire the full list above; flip coverage gate per CLAUDE.md
  pending list.

---

## 9. PII drop policy — verified

The existing `_drop_pii` processor in `utils/logging.py` drops these keys
**before JSON render**:

```python
_PII_KEYS = frozenset({
    "prompt", "response", "document", "email", "phone",
    "raw_content", "english_translation", "original_language",
    "password", "api_key", "token",
})
```

**Verification against `.claude/rules/logging.md` §5:** identical set. ✓

**Order in the chain (§7.3):**

```
merge_contextvars -> _add_request_id -> _add_trace_context ->
add_log_level -> _rename_level_to_severity -> _drop_pii ->
TimeStamper -> wrap_for_formatter
```

`_drop_pii` sits immediately before `TimeStamper` and the final formatter.
Anything added by preceding processors is still subject to the drop. ✓

**Span-side PII drop:** OTel spans have no automatic drop. The defense is
"don't put banned keys on spans in the first place." The only span
attributes we set (§5 table) are bounded, typed, and non-PII — `agent.name`,
`tool.name`, token counts, the exception ULID, durations. No raw prompts,
no message bodies.

**Negative test** in the observability test suite (§14) asserts that after
calling `audit_event("...", prompt="leaked", email="a@b.com")`, the captured
log entry has neither `prompt` nor `email` keys.

---

## 10. Cloud Trace dashboard setup (pre-demo)

Three artifacts to prepare before demo day so the judge sees a polished view.

### 10.1 Service map

Cloud Console -> Trace -> Explore -> Service map tab. It renders
`service.name=sct-triage` as a node with downstream Gemini API calls. Zero
config — appears after the first trace lands.

### 10.2 Saved trace-list filter

Cloud Console -> Trace -> Trace Explorer. Filter:

```
service.name = "sct-triage"
span.name = "POST /triage/submit"
```

Click "Save" -> name it "Triage demo runs". Share the URL with the judge.

### 10.3 Waterfall screenshot for the slides

Kick off one run against the `NH-48` test fixture, wait ~5s for the span to
flush, open the trace, expand all children. Screenshot the waterfall —
every span carrying `gen_ai.usage.*` attributes. Drop into the demo deck at
slide 8 ("Observability + Cost Attribution").

### 10.4 `gcloud` alternative (if console is rate-limited)

```bash
# List recent traces for the service.
gcloud trace list \
  --project=sct-prod \
  --filter='span.name=agent.classifier' \
  --limit=20 \
  --format='table(traceId,spans[0].startTime,spans[0].durationNanos)'
```

Handy for verification from a terminal during a demo rehearsal.

---

## 11. Cloud Monitoring dashboards

Tier 1 dashboards are **log-based metrics** (no OTel metrics pipeline yet).
Log-based metrics are derived from the structured log events; every field in
our JSON payload is queryable.

### 11.1 Metrics to create

Cloud Console -> Logging -> Log-based Metrics -> Create metric.

| Metric name | Type | Filter | Label extractors |
|---|---|---|---|
| `sct_agent_invocations` | counter | `jsonPayload.event="agent_invoked"` | `agent_name := jsonPayload.agent_name` |
| `sct_agent_latency_ms` | distribution | `jsonPayload.event="agent_invoked"` | `agent_name`; value `= jsonPayload.duration_ms` |
| `sct_tokens_in` | counter (int64) | `jsonPayload.event="agent_invoked"` | `agent_name`; value `= jsonPayload.tokens_in` |
| `sct_tokens_out` | counter (int64) | same | same |
| `sct_tool_errors` | counter | `jsonPayload.event="tool_invoked" AND jsonPayload.status="error"` | `tool_name`, `agent_name` |
| `sct_firestore_ops` | counter | `jsonPayload.event="firestore_op"` | `op`, `collection` |
| `sct_rate_limit_hits` | counter | `jsonPayload.event="rate_limit_hit"` | `user_id` |

### 11.2 Dashboard panels (MQL)

Dashboard: **sct-triage-overview**. Five panels.

**Panel 1 — Request rate + latency p50/p95/p99.** MQL:

```mql
fetch cloud_run_revision
| metric 'logging.googleapis.com/user/sct_agent_latency_ms'
| align delta(1m)
| every 1m
| group_by [metric.agent_name], [
    val_p50: percentile(value.sct_agent_latency_ms, 50),
    val_p95: percentile(value.sct_agent_latency_ms, 95),
    val_p99: percentile(value.sct_agent_latency_ms, 99),
  ]
```

**Panel 2 — Token burn per agent per hour.**

```mql
fetch cloud_run_revision
| metric 'logging.googleapis.com/user/sct_tokens_in'
| align rate(1h)
| every 1m
| group_by [metric.agent_name], [tokens_in_per_hr: sum(value.sct_tokens_in)]
```

(Repeat with `sct_tokens_out` for the output-token panel.)

**Panel 3 — Firestore ops per agent per hour.**

```mql
fetch cloud_run_revision
| metric 'logging.googleapis.com/user/sct_firestore_ops'
| align rate(1h)
| every 1m
| group_by [metric.collection, metric.op],
    [ops_per_hr: sum(value.sct_firestore_ops)]
```

Catches the N+1 question the rule file §8 is explicitly about: when
`ops_per_hr` jumps sharply without `sct_agent_invocations` changing, an
agent loop is fanning out.

**Panel 4 — 429 rate-limit hits (per-uid).**

```mql
fetch cloud_run_revision
| metric 'logging.googleapis.com/user/sct_rate_limit_hits'
| align rate(5m)
| every 1m
| group_by [metric.user_id], [hits: sum(value.sct_rate_limit_hits)]
```

**Panel 5 — Budget burn (real $).** Cloud Billing export to BigQuery, then:

```mql
fetch global
| metric 'billing.googleapis.com/project/cost'
| filter resource.project_id == 'sct-prod'
| align rate(1h)
| group_by [resource.service], [hourly_cost: sum(value.cost)]
```

Requires billing export on (free; opt-in per project).

---

## 12. Budget alerts — $10 / $25 / $50 email

Three thresholds on one budget. The money total is the demo-week cap; the
intermediate alerts catch a runaway loop before it hits the wall.

### 12.1 Console click-path (easier for demo-day setup)

1. Cloud Console -> Billing -> Budgets & alerts -> Create budget.
2. Scope: "Projects" -> `sct-prod` only (not the billing account as a whole —
   keeps other hobby projects' spend separate).
3. Amount: `$50 USD`. Monthly period.
4. Thresholds: `20% (= $10)`, `50% (= $25)`, `100% (= $50)`.
5. Notifications: tick "Email alerts to billing admins".
6. Save.

### 12.2 `gcloud` form for repeatability

```bash
gcloud billing budgets create \
  --billing-account=01ABCD-EFGH23-456789 \
  --display-name="sct-prod-monthly" \
  --budget-amount=50USD \
  --filter-projects="projects/sct-prod" \
  --threshold-rule=percent=0.2 \
  --threshold-rule=percent=0.5 \
  --threshold-rule=percent=1.0 \
  --all-updates-rule-monitoring-notification-channels=projects/sct-prod/notificationChannels/$CHANNEL_ID \
  --all-updates-rule-disable-default-iam-recipients=false
```

Swap `BILLING_ACCOUNT_ID` for your real billing account (looks like
`01ABCD-EFGH23-456789`). `CHANNEL_ID` is the Monitoring notification channel
ID for your email; create one via:

```bash
gcloud beta monitoring channels create \
  --display-name="sct-ops-email" \
  --type=email \
  --channel-labels=email_address=ops@example.com
```

### 12.3 Optional — Pub/Sub kill-switch

For Tier 2, upgrade to the Pub/Sub form:

```bash
gcloud billing budgets create \
  --billing-account=01ABCD-EFGH23-456789 \
  --display-name="sct-prod-killswitch" \
  --budget-amount=50USD \
  --filter-projects="projects/sct-prod" \
  --threshold-rule=percent=1.0,basis=current-spend \
  --notifications-pubsub-topic="projects/sct-prod/topics/budget-alerts" \
  --notifications-pubsub-enable
```

Subscribe a Cloud Function that calls `services.disable()` on Gemini +
Firestore. Deferred — three email thresholds suffice for the hackathon
window.

---

## 13. SIGTERM shutdown — the one thing that makes or breaks the demo

Cloud Run sends `SIGTERM` to the container ~10 seconds before `SIGKILL`.
Without a handler:

- `BatchSpanProcessor` has up to `schedule_delay_millis=5000` (our config)
  of buffered spans at any moment.
- The in-flight span (`agent.classifier`) is flushed only when it ends.
  That's fine; the problem is spans already ended and sitting in the
  processor's queue.
- Cloud Run SIGKILL -> process dies -> queue discarded -> **final trace
  loses spans**.

The §3 code installs a single handler that calls `provider.shutdown()`:

```python
def _shutdown(*_: object) -> None:
    provider.shutdown()

signal.signal(signal.SIGTERM, _shutdown)
signal.signal(signal.SIGINT, _shutdown)
```

`provider.shutdown()` internally:

1. Calls `force_flush()` on every processor — drains the queue to the
   exporter with a 5s timeout (our `export_timeout_millis`).
2. Shuts down each processor's worker thread.
3. Sets `_shutdown_called=True` so the `atexit` hook (registered
   automatically by `BatchSpanProcessor`) is a no-op on the second call.

Double-call protection: safe to call from both the signal handler and the
`atexit` hook. `_shutdown_called` gates both paths.

**Local dev note:** `SIGINT` (Ctrl+C) triggers the same shutdown so that
`uv run uvicorn ...` during iteration doesn't leak spans into the next run.

**Kubernetes / Agent Engine (future):** both send SIGTERM; same handler
works. If we ever deploy to GKE with a longer preStop hook, raise the export
timeout to 8s and shorten the signal handler's grace — tradeoff goes the
other way.

---

## 14. Observability testing

Two new test files. Neither hits real GCP.

### 14.1 `tests/unit/core/test_tracing.py`

Asserts spans are emitted for every agent invocation, with the right
attributes, using `InMemorySpanExporter`.

```python
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)


@pytest.fixture
def span_exporter():
    """Wire a fresh TracerProvider with an in-memory exporter for this test."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    yield exporter
    exporter.clear()


def test_classifier_emits_agent_span_with_token_attributes(span_exporter):
    """agent.classifier span carries GenAI semconv attrs + tokens + duration."""
    from supply_chain_triage.core.tracing import (
        end_agent_span,
        start_agent_span,
    )

    span = start_agent_span(name="classifier", model="gemini-2.5-flash")
    end_agent_span(span, tokens_in=1284, tokens_out=97, duration_ms=842.0)

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    s = spans[0]
    assert s.name == "agent.classifier"
    assert s.attributes["agent.name"] == "classifier"
    assert s.attributes["gen_ai.provider.name"] == "gcp.gemini"
    assert s.attributes["gen_ai.operation.name"] == "chat"
    assert s.attributes["gen_ai.request.model"] == "gemini-2.5-flash"
    assert s.attributes["gen_ai.usage.input_tokens"] == 1284
    assert s.attributes["gen_ai.usage.output_tokens"] == 97
    assert s.attributes["duration_ms"] == pytest.approx(842.0)
```

### 14.2 `tests/unit/utils/test_logging_trace_correlation.py`

Asserts the three magic fields appear in the log event when a span is active,
and that PII still drops:

```python
import structlog
from opentelemetry import trace

from supply_chain_triage.utils.logging import get_logger


def test_log_event_gets_trace_and_span_ids(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "sct-test")
    capture = structlog.testing.LogCapture()
    structlog.configure(processors=[capture])

    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("fake_parent"):
        get_logger(__name__).info("probe", tokens_in=42)

    entry = capture.entries[-1]
    assert entry["event"] == "probe"
    assert entry["tokens_in"] == 42
    assert "logging.googleapis.com/trace" in entry
    assert "logging.googleapis.com/spanId" in entry
    assert entry["logging.googleapis.com/trace"].startswith("projects/sct-test/traces/")


def test_pii_fields_still_dropped(monkeypatch):
    capture = structlog.testing.LogCapture()
    structlog.configure(processors=[capture])
    get_logger(__name__).info(
        "probe", prompt="leaked", email="a@b.com", safe_field=1,
    )
    entry = capture.entries[-1]
    assert "prompt" not in entry
    assert "email" not in entry
    assert entry["safe_field"] == 1
```

These two tests run in `tests/unit/` — no emulators, no network. CI safe.

### 14.3 Audit-event canonical list sanity test

`tests/unit/middleware/test_audit_event_canonical.py` — asserts that the
exact event names in `.claude/rules/observability.md` §6 are emitted from
the right call sites. Grep-based, cheap, catches drift:

```python
import ast
from pathlib import Path

CANONICAL_EVENTS = {
    "auth_login", "auth_failure", "permission_denied", "rate_limit_hit",
    "agent_invoked", "agent_completed", "tool_invoked",
    "classification_result", "escalation_triggered", "secret_rotated",
}

def test_all_canonical_audit_events_exist_in_code():
    roots = Path("src/supply_chain_triage").rglob("*.py")
    emitted = set()
    for p in roots:
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                name = getattr(fn, "attr", None) or getattr(fn, "id", None)
                if name in {"audit_event", "info", "log_agent_invocation"}:
                    if node.args and isinstance(node.args[0], ast.Constant):
                        emitted.add(node.args[0].value)
    # Tier 1 minimum set — tighten at Tier 2.
    required_now = {"agent_invoked", "classification_result"}
    missing = required_now - emitted
    assert not missing, f"Canonical events missing: {missing}"
```

---

## 15. Demo walkthrough — the artifact that makes the judge nod

The point of Tier 1 observability is **one screenshot** that tells the
whole cost + latency story in 10 seconds.

**Preparation (day-of):**

1. `uv run adk web src/supply_chain_triage/modules/triage/agents` — warm
   the local environment so the Gemini quota is primed.
2. Run one prompt end-to-end against the seeded NH-48 fixture.
3. Confirm Cloud Trace has the trace (Cloud Run -> sct-prod service ->
   Logs -> find the `agent_invoked` line -> click the trace link).
4. Open the trace waterfall. Expand every child.
5. Screenshot and drop in slide 8.

**What the judge sees:**

- Root span `POST /triage/submit` — 2.3s.
- Child `agent.classifier` — 0.9s, `gen_ai.usage.input_tokens=1284`,
  `output_tokens=97`.
- Inside it, ADK's two `call_llm` spans (fetcher + formatter) nested.
- Tool spans `tool.get_exception_event`, `tool.get_company_profile` as
  siblings under fetcher.
- Sibling `agent.impact` — 1.3s, `tokens_in=3102`, `tokens_out=184`.

**What to say out loud:**

> "Every agent and every tool is a span with token counts. I can point at
> any box in this waterfall and tell you how much it cost. Today it was
> 4386 input tokens, 281 output tokens — at Gemini 2.5 Flash rates,
> roughly $0.003 per triage. The $50 budget alert covers 16000 such runs."

**Fallback artifact if live cloud is flaky** — the test in §14.1 prints
span attributes; run it locally during the demo:

```bash
uv run pytest tests/unit/core/test_tracing.py -s -v
```

Shows the same attributes in the terminal. Not as pretty as the waterfall
but proves the wiring.

---

## 16. Concrete next-session task list (file-by-file)

Ordered by dependency — do in sequence, each step leaves the tree green.

### Step 1 — pyproject + uv lock

- [ ] `pyproject.toml` — add the six OTel packages in §2 under main
      `dependencies`.
- [ ] `uv add ...` + `uv sync --locked`. Commit `uv.lock`.

### Step 2 — create `core/tracing.py`

- [ ] New file `src/supply_chain_triage/core/tracing.py` with the §3 body
      plus the §4.1 helpers (`start_agent_span`, `end_agent_span`,
      `start_tool_span`, `end_tool_span`).
- [ ] No per-file ruff exceptions needed (OTel isn't in the TID251 banned
      list).

### Step 3 — update `utils/logging.py`

- [ ] Add `_add_trace_context` processor (§7.1).
- [ ] Add `_rename_level_to_severity` processor (§7.2).
- [ ] Insert into the `structlog.configure(processors=[...])` chain per §7.3.
- [ ] File is already at ~440 lines with a 500-line soft limit — OK.

### Step 4 — wire `lifespan` in `main.py`

- [ ] Convert `create_app()` to pass an `asynccontextmanager lifespan` per
      §3.
- [ ] Call `configure_tracing(app)` inside the lifespan before yielding.
- [ ] Keep the existing middleware stack order (load-bearing per
      `.claude/rules/security.md` §9 — documented inline).

### Step 5 — instrument classifier agent

- [ ] `modules/triage/agents/classifier/agent.py` — imports from
      `core.tracing`, new `_STATE_SPAN` key, updated `_before_agent` /
      `_after_agent`, new `_before_tool` / `_after_tool` callbacks wired
      into the fetcher (§4.2, §4.3).

### Step 6 — instrument impact agent

- [ ] Same surgery in `modules/triage/agents/impact/agent.py`. Six tools
      on the fetcher — same state-key pattern (§4.4).

### Step 7 — harden `audit_event` (deferred mini-task)

- [ ] `middleware/audit_log.py` — upgrade signature to enforce
      `correlation_id` / `user_id` / `company_id` with `ValueError` on
      empty.
- [ ] Emit `classification_result` from the classifier's `_after_agent`
      after post-rules (§8.3 now-list).
- [ ] Emit `agent_completed` as a distinct event in `_after_agent` (in
      addition to the current `agent_invoked` emission in
      `log_agent_invocation`).

### Step 8 — tests

- [ ] `tests/unit/core/test_tracing.py` per §14.1.
- [ ] `tests/unit/utils/test_logging_trace_correlation.py` per §14.2.
- [ ] `tests/unit/middleware/test_audit_event_canonical.py` per §14.3.

### Step 9 — dashboards + budget

- [ ] Create the seven log-based metrics from §11.1 via console
      (`gcloud logging metrics create` works too, but console is quicker
      for Tier 1).
- [ ] Create dashboard "sct-triage-overview" with the five MQL panels
      (§11.2).
- [ ] Create budget "sct-prod-monthly" per §12.

### Step 10 — rehearsal

- [ ] End-to-end run against NH-48 fixture in `sct-prod`.
- [ ] Confirm trace waterfall matches §4.5 expected shape.
- [ ] Confirm log rows click through to trace via the magic fields.
- [ ] Screenshot for the demo slide.

### Step 11 — session log

- [ ] `docs/sessions/2026-04-18-observability-otel-cloud-trace.md` with
      decisions + rationale + next steps, per CLAUDE.md "Session notes
      discipline".

---

## 17. Sources + dates

All fetched in April 2026 for this research session.

### Specifications

- [OpenTelemetry GenAI semantic conventions (top)](https://opentelemetry.io/docs/specs/semconv/gen-ai/) — status: Development.
- [GenAI client spans](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/) — `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.response.*`, `gen_ai.usage.*`.
- [GenAI agent + framework spans](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/) — naming and requirement levels for agent/framework emissions.
- [GenAI metrics](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-metrics/) — token usage histogram conventions.
- [GenAI attribute registry](https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/) — canonical attribute reference.

### Google Cloud documentation

- [Instrument ADK apps with OpenTelemetry](https://docs.cloud.google.com/stackdriver/docs/instrumentation/ai-agent-adk) — `adk web --otel_to_cloud`, built-in `call_llm` spans in ADK >=1.17.
- [Python instrumentation sample for Cloud Trace](https://docs.cloud.google.com/trace/docs/setup/python-ot) — canonical TracerProvider + BatchSpanProcessor + OTLP exporter setup.
- [Cloud Trace Exporter Example](https://google-cloud-opentelemetry.readthedocs.io/en/latest/examples/cloud_trace_exporter/README.html) — `CloudTraceSpanExporter` API details.
- [Structured logging in Cloud Logging](https://docs.cloud.google.com/logging/docs/structured-logging) — the three magic `logging.googleapis.com/*` fields.
- [Link log entries with traces](https://docs.cloud.google.com/trace/docs/trace-log-integration) — auto-correlation mechanism.
- [Cloud Run container runtime contract (SIGTERM handler)](https://docs.cloud.google.com/run/docs/samples/cloudrun-sigterm-handler) — the 10-second grace period.
- [Create budget alerts](https://docs.cloud.google.com/billing/docs/how-to/budgets) — `gcloud billing budgets create`.
- [Programmatic budget notifications](https://docs.cloud.google.com/billing/docs/how-to/budgets-programmatic-notifications) — `--notifications-pubsub-topic`.

### Python SDK + exporters

- [opentelemetry-exporter-gcp-trace on PyPI](https://pypi.org/project/opentelemetry-exporter-gcp-trace/)
- [GoogleCloudPlatform/opentelemetry-operations-python](https://github.com/GoogleCloudPlatform/opentelemetry-operations-python)
- [opentelemetry-python — SpanProcessor + export module](https://opentelemetry-python.readthedocs.io/en/latest/sdk/trace.export.html)
- [opentelemetry-instrumentation-google-genai on PyPI](https://pypi.org/project/opentelemetry-instrumentation-google-genai/) — evaluated, deferred for Tier 1 (ADK already instruments `call_llm`).

### Secondary references

- [OpenTelemetry for AI Systems (Uptrace 2026 overview)](https://uptrace.dev/blog/opentelemetry-ai-systems)
- [Correlate Cloud Trace spans with Cloud Logging (OneUptime 2026-02-17)](https://oneuptime.com/blog/post/2026-02-17-how-to-correlate-cloud-trace-spans-with-cloud-logging-entries-for-end-to-end-debugging/view)
- [OTel SDK shutdown with atexit + SIGTERM (OneUptime 2026-02-06)](https://oneuptime.com/blog/post/2026-02-06-otel-sdk-shutdown-python-atexit-sigterm/view)
- [Structured logging via Google Cloud Logging Python v3.0.0 (Medium, Sanche)](https://medium.com/google-cloud/introducing-google-cloud-logging-python-v3-0-0-4c548663bab4)

### Internal project rules referenced

- `.claude/rules/observability.md` — §1 (span attrs), §3 (SIGTERM), §4 (structured JSON), §5 (PII), §6 (`audit_event`), §7 (cost attribution), §8 (Firestore op counting), §9 (retention).
- `.claude/rules/logging.md` — §1 (entry point), §4 (domain helpers), §5 (PII), §6 (request-id propagation), §7 (test pattern), §8 (file vs stdout).
- `.claude/rules/security.md` — §6 (no secret read at import time), §9 (middleware stack order).
- `.claude/rules/agents.md` — §1 (callback placement), §2 (state namespacing, `temp:` prefix).
- `.claude/rules/architecture-layers.md` — §2 (utils/logging.py narrow exception).

### Existing repo files analyzed

- `src/supply_chain_triage/main.py` — current `create_app` + middleware stack.
- `src/supply_chain_triage/utils/logging.py` — existing processor chain + PII drop + stdout JSON handler.
- `src/supply_chain_triage/middleware/audit_log.py` — existing `audit_event` helper + `AuditLogMiddleware`.
- `src/supply_chain_triage/modules/triage/agents/classifier/agent.py` — existing callback lifecycle, token accumulation pattern.
- `src/supply_chain_triage/modules/triage/agents/impact/agent.py` — same pattern as classifier.
- `pyproject.toml` — current dep set (no OTel packages yet).

---

## Appendix A — alternatives considered and rejected

| Alternative | Why rejected for Tier 1 |
|---|---|
| OTel Collector sidecar on Cloud Run | Adds a container + a config file + a port. CloudTraceSpanExporter direct is one less moving part. Revisit at Tier 2 if we fan out to multiple exporters. |
| OTLP gRPC -> Cloud Trace via Managed Collector | Google's managed collector is GA but requires VPC configuration in `asia-south1`. The direct SDK exporter needs only the `cloudtrace.spans.write` IAM role on the Cloud Run service account. |
| `opentelemetry-instrumentation-google-genai` | Double-counts `call_llm` with ADK's built-in span. Re-evaluate if we ever call Gemini outside ADK (e.g. a fast-path tool-less classifier). |
| `google-cloud-logging` Python SDK handler | Pairs a second log pipe (API calls to Cloud Logging) alongside Cloud Run's built-in stdout scraper. Doubles the cost of logs. Stdout JSON is already the documented path. |
| BigQuery log sink | Nothing to query against for Tier 1 — no historical baseline. Turn on at Tier 2 when we have a week of traffic. |
| Grafana / external Tempo backend | Another hosted service, another credential, another piece for the judge to be confused by. Cloud Trace covers the demo. |
| Manual span creation inside tools | Tool callbacks (`before_tool_callback` / `after_tool_callback`) are the ADK-blessed integration point. Wrapping inside the tool function works but leaks OTel imports into `tools.py`, which future framework swaps hate. |

## Appendix B — what Tier 2 / 3 adds

Roughly, in order:

1. **OTel metrics pipeline** — direct Gemini-cost metric instead of
   log-based. Needs `opentelemetry-exporter-gcp-monitoring` + a
   `MeterProvider` next to `TracerProvider`. One histogram
   `sct.agent.tokens` with attributes `{agent.name, direction}`.
2. **Cross-agent A2A traceparent propagation** — Tier 3 will expose agents
   via A2A. ADK emits them as separate HTTP hops. The
   `TraceContextTextMapPropagator` already installed (§3) covers this;
   no code change.
3. **BigQuery log sink + Looker Studio** — historical token burn
   dashboards survive past Cloud Logging's 30-day retention.
4. **Pub/Sub kill-switch** — auto-disable Gemini if monthly budget
   crosses 100%. §12.3 draft.
5. **Agent Engine OTel forwarding** — if we ever shift from Cloud Run to
   Vertex AI Agent Engine, Agent Engine forwards OTel natively; the
   `configure_tracing` module becomes a no-op on Agent Engine.
6. **`adk eval` trace viewer integration** — ADK's eval runner can pull
   traces from Cloud Trace for a given session ID; helps debug validation
   failures during eval runs.

---

*End of research document.*

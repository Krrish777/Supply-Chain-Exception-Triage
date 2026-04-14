---
description: Mandatory usage of supply_chain_triage.utils.logging.get_logger — no print(), no raw stdlib/structlog.get_logger()
paths: ["src/**", "tests/**", "scripts/**"]
---

# Logging rules

The canonical logging entry point is `supply_chain_triage.utils.logging.get_logger`. Everything else is forbidden.

## 1. The one entry point

```python
from supply_chain_triage.utils.logging import get_logger

logger = get_logger(__name__)
logger.info("event_name", key=value, other_key=other_value)
```

- **Always** `__name__` at the call site. The logger auto-prefixes with `supply_chain_triage.` if the name doesn't start with it.
- Always call `.info("event_name", **kwargs)` — positional is the event name (snake_case verb); kwargs are the structured context.
- **Never** `logger.info(f"something with {variable}")` — f-strings lose structure. Pass `variable=variable` as a kwarg instead.

## 2. Banned alternatives

Enforced by ruff (`T20`) + code review:

| Don't | Do instead |
|---|---|
| `print(...)` | `logger.info("event_name", ...)` |
| `pprint(...)` | `logger.debug("event_name", data=...)` (pretty-rendered by Rich at DEBUG) |
| `logging.getLogger(__name__)` | `get_logger(__name__)` |
| `structlog.get_logger(__name__)` | `get_logger(__name__)` |
| `sys.stderr.write(...)` | `logger.warning("event_name", ...)` |

**Scripts exception:** `scripts/*.py` may use `print()` for operator-facing CLI output (the per-file-ignore in `pyproject.toml` allows this). Tools + middleware + agent code — never.

## 3. Log levels

Use the narrowest level that accurately describes the event:

| Level | When | Example |
|---|---|---|
| `debug` | Per-operation verbose trace | `logger.debug("query_issued", query=q)` |
| `info` | Lifecycle events worth keeping | `logger.info("agent_invoked", agent_name="classifier")` |
| `warning` | Unexpected but handled; degraded behavior | `logger.warning("retry_started", attempt=2)` |
| `error` | Handled failure; caller will see an error path | `logger.error("tool_failed", tool_name="x", error_class="ConnectionError")` |
| `exception` | Unhandled exception (logger captures traceback) | `logger.exception("unhandled")` inside `except:` |

Never use `critical` unless the process is about to crash.

## 4. Domain helpers — prefer when applicable

`utils/logging.py` exposes typed helpers. Use them over raw `.info()` for standardized events:

- `log_agent_invocation(agent_name, duration_ms, tokens_in=..., tokens_out=..., **extra)` — agent boundaries.
- `log_tool_call(tool_name, agent_name, duration_ms, status, **extra)` — tool boundaries.
- `log_firestore_op(op, collection, doc_count, duration_ms, **extra)` — Firestore access (catches N+1).
- `log_api_call(method, endpoint, status_code, duration_ms)` — HTTP ingress.
- `log_auth_event(action, uid=..., details=...)` — auth lifecycle.

These emit consistent field names so dashboards + cost attribution work without per-site translation.

## 5. PII — never passed in

Fields named `prompt`, `response`, `document`, `email`, `phone`, `raw_content`, `english_translation`, `original_language`, `password`, `api_key`, `token` are **dropped** by the processor chain before any handler sees them (defense-in-depth).

But the drop processor is a safety net, not an excuse. **Don't pass PII fields in the first place.** Pass the `exception_id` / `user_id` / `company_id` and let consumers look up the full content elsewhere (Firestore) if they need it.

Full allowlist of loggable field names: `security.md` §7.

## 6. Request ID propagation

The project-wide `request_id` is managed via `structlog.contextvars` — bound once by the outermost middleware, inherited automatically by every downstream `get_logger(...)` call in the same request (sync or async).

```python
# In AuditLogMiddleware (or equivalent):
import structlog
from supply_chain_triage.utils.logging import generate_request_id

async def dispatch(self, request, call_next):
    structlog.contextvars.clear_contextvars()           # fresh per request
    structlog.contextvars.bind_contextvars(request_id=generate_request_id())
    return await call_next(request)
```

Downstream:
```python
logger = get_logger(__name__)
logger.info("something")  # automatically includes request_id
```

**Don't** call `request_id_var.set(...)` from application code. It's exposed for stdlib-compat (uvicorn access logs) only.

## 7. Test pattern — capturing logs

Use structlog's testing utilities:

```python
import structlog
import pytest

@pytest.fixture
def log_output():
    """Capture structured log events for assertions."""
    output = structlog.testing.LogCapture()
    structlog.configure(processors=[output])
    try:
        yield output
    finally:
        # Restore default config (or re-call utils.logging._configure_once to reset).
        pass
```

Then in tests:
```python
def test_something(log_output):
    do_the_thing()
    assert any(e["event"] == "expected_event" for e in log_output.entries)
```

**Don't** assert on formatted strings — assert on `entries[i]["event"]` + specific keys. String matching breaks when PII redaction changes.

## 8. File vs stdout handlers

Controlled by env var `LOG_TO_FILES`:
- `LOG_TO_FILES=1` (default): Rich console + 4 rotating file handlers in `logs/`.
- `LOG_TO_FILES=0` (Cloud Run): Rich console + JSON stdout only. Files skipped.

Set this in Cloud Run's env config; local dev leaves it unset.

## 9. Anti-patterns

- `print("DEBUG: ...")` for quick debugging — use `logger.debug`.
- `logger.info(f"got {x} results")` — loses the `results_count=x` kwarg.
- `logger.info("fetched data", data=big_firestore_doc)` — log a summary (doc ID + count), not the content.
- Creating a new logger per request.
- Configuring `structlog.configure()` outside `utils/logging.py`.
- Logging full exception objects when `.exception()` does it for you.
- Using `log_agent_invocation` without `duration_ms` — mandatory for cost attribution.

## 10. Related rules

- `.claude/rules/observability.md` — OTel spans, cost attribution, PII redaction, retention.
- `.claude/rules/security.md` §7 — PII-safe field allowlist (which this rule enforces in code).
- `.claude/rules/architecture-layers.md` §2 — the narrow exception that lets `utils/logging.py` import `structlog` + `rich`.

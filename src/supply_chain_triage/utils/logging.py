"""Canonical logging entry point for the project.

Every module imports from here; no code may call ``logging.getLogger()``,
``structlog.get_logger()``, or ``print()`` directly. See
``.claude/rules/logging.md``.

## Architecture

``structlog`` bridged to stdlib ``logging`` via
``structlog.stdlib.ProcessorFormatter``. ``structlog`` manages the processor
chain (contextvars, PII drop, timestamper, JSON or console renderer); stdlib
handlers manage the sinks.

- **Console**: Rich-powered — colored, wrapped, with rich tracebacks.
- **`logs/app.log`** (daily rotation, 30-day retention): human-readable line
  per event.
- **`logs/app.json.log`** (daily rotation, 30-day retention): structured JSON
  for machine consumption / Cloud Logging-compatible querying.
- **`logs/error.log`** (size rotation, 10 MB x 5): ERROR+ only, for triage.
- **`logs/api.log`** (daily rotation, 30-day retention): API access log
  (HTTP ingress / egress).

In production (``LOG_TO_FILES=0``), file handlers skip registration; console +
JSON stdout only — matches the Cloud Run logging pipeline.

## Usage

```python
from supply_chain_triage.utils.logging import get_logger
logger = get_logger(__name__)
logger.info("agent_invoked", agent_name="classifier", duration_ms=42, tokens_in=512)
```

## PII protection

Fields named ``prompt``, ``response``, ``document``, ``email``, ``phone``,
``raw_content``, ``english_translation``, ``original_language``, ``password``,
``api_key``, ``token`` are DROPPED by the processor chain before any handler
sees them. See ``.claude/rules/security.md`` §7 for the canonical list.

## Why ``utils/`` is the right home

``utils/`` is the lowest layer — every other module can import from it. The
architecture-layers rule (``.claude/rules/architecture-layers.md``) allows
``rich`` / ``structlog`` / ``logging.handlers`` *only* in this file; they are
logging-infrastructure deps, not general app deps.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import structlog

if TYPE_CHECKING:
    from collections.abc import MutableMapping
from rich.console import Console
from rich.logging import RichHandler
from rich.traceback import install as install_rich_traceback

# --- ContextVar for cross-async request correlation --------------------------
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# --- Config (read at setup time only; per observability.md §9) --------------
_LOGS_DIR = Path(os.getenv("LOGS_DIR", "logs"))
_LOG_LEVEL_NAME = os.getenv("LOG_LEVEL", "INFO").upper()
_LOG_TO_FILES = os.getenv("LOG_TO_FILES", "1") != "0"

# --- PII drop keys (security.md §7) -----------------------------------------
_PII_KEYS = frozenset(
    {
        "prompt",
        "response",
        "document",
        "email",
        "phone",
        "raw_content",
        "english_translation",
        "original_language",
        "password",
        "api_key",
        "token",
    }
)


def _drop_pii(
    _logger: Any,
    _method: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """structlog processor: drop any PII key before rendering."""
    for k in list(event_dict):
        if k in _PII_KEYS:
            event_dict.pop(k, None)
    return event_dict


def _add_request_id(
    _logger: Any,
    _method: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """structlog processor: inject request_id from the raw ContextVar.

    Primary request_id propagation uses ``structlog.contextvars.bind_contextvars``
    (handled by the built-in ``merge_contextvars`` processor earlier in the
    chain). This processor is a fallback for stdlib-only log records
    (uvicorn, warnings) that don't know about structlog's contextvars — it
    copies the raw ``request_id_var`` into the event dict if nothing set it.
    See ``docs/research/Supply-Chain-Zettel-Structlog-Async-Contextvars``.
    """
    event_dict.setdefault("request_id", request_id_var.get())
    return event_dict


# --- Handler factories -------------------------------------------------------

_CONSOLE_FORMAT = "%(message)s"
_FILE_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | [%(request_id)s] %(message)s"
_ERROR_FORMAT = (
    "%(asctime)s | %(name)s | %(levelname)s | [%(request_id)s] %(message)s\n"
    "%(pathname)s:%(lineno)d"
)
_DATEFMT = "%Y-%m-%d %H:%M:%S"


class _RequestIdFilter(logging.Filter):
    """Inject ``request_id`` onto stdlib-only records (uvicorn, etc.)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = request_id_var.get()
        return True


def _rich_console_handler(level: int) -> logging.Handler:
    console = Console(stderr=True, force_terminal=True)
    # `tracebacks_show_locals=True` exposes local variable values per frame —
    # DEV ONLY (DEBUG level). Even at DEBUG, cap each local via
    # locals_max_string + locals_max_length — defense-in-depth against
    # accidental PII / token / long-prompt dumps (security.md §7).
    handler = RichHandler(
        console=console,
        show_time=True,
        show_level=True,
        show_path=True,
        markup=True,
        rich_tracebacks=True,
        tracebacks_show_locals=level == logging.DEBUG,
        tracebacks_suppress=["uvicorn", "starlette", "fastapi"],
        locals_max_string=80,
        locals_max_length=10,
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_CONSOLE_FORMAT, datefmt="[%X]"))
    handler.addFilter(_RequestIdFilter())
    return handler


def _app_file_handler() -> logging.Handler:
    handler = logging.handlers.TimedRotatingFileHandler(
        _LOGS_DIR / "app.log",
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(_FILE_FORMAT, datefmt=_DATEFMT))
    handler.addFilter(_RequestIdFilter())
    return handler


def _error_file_handler() -> logging.Handler:
    handler = logging.handlers.RotatingFileHandler(
        _LOGS_DIR / "error.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setLevel(logging.ERROR)
    handler.setFormatter(logging.Formatter(_ERROR_FORMAT, datefmt=_DATEFMT))
    handler.addFilter(_RequestIdFilter())
    return handler


def _json_file_handler() -> logging.Handler:
    handler = logging.handlers.TimedRotatingFileHandler(
        _LOGS_DIR / "app.json.log",
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    handler.setLevel(logging.DEBUG)
    # JSON rendering is handled by structlog's processor chain; for stdlib-only
    # records (uvicorn), we render the minimal JSON ourselves.
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=[
                structlog.processors.TimeStamper(fmt="iso", utc=True),
                structlog.processors.add_log_level,
            ],
        ),
    )
    handler.addFilter(_RequestIdFilter())
    return handler


def _api_file_handler() -> logging.Handler:
    handler = logging.handlers.TimedRotatingFileHandler(
        _LOGS_DIR / "api.log",
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | [%(request_id)s] %(message)s",
            datefmt=_DATEFMT,
        ),
    )
    handler.addFilter(_RequestIdFilter())
    return handler


def _stdout_json_handler() -> logging.Handler:
    """Cloud Run writes stdout → Cloud Logging. JSON on stdout in prod."""
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setLevel(logging.INFO)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=[
                structlog.processors.TimeStamper(fmt="iso", utc=True),
                structlog.processors.add_log_level,
            ],
        ),
    )
    handler.addFilter(_RequestIdFilter())
    return handler


# --- Configure once, idempotent ---------------------------------------------


def _configure_once() -> None:
    """Idempotent setup. Safe to call many times — only the first call acts.

    Uses a function attribute instead of a module-global to sidestep PLW0603
    while keeping the module import-safe.
    """
    if getattr(_configure_once, "_done", False):
        return
    _configure_once._done = True  # type: ignore[attr-defined]

    level = getattr(logging, _LOG_LEVEL_NAME, logging.INFO)

    install_rich_traceback(
        show_locals=level == logging.DEBUG,
        suppress=["uvicorn", "starlette", "fastapi"],
    )

    handlers: list[logging.Handler] = [_rich_console_handler(level)]
    if _LOG_TO_FILES:
        _LOGS_DIR.mkdir(exist_ok=True)
        handlers.append(_app_file_handler())
        handlers.append(_error_file_handler())
        handlers.append(_json_file_handler())
        handlers.append(_api_file_handler())
    else:
        # Cloud Run — JSON to stdout (captured by Cloud Logging).
        handlers.append(_stdout_json_handler())

    root = logging.getLogger("supply_chain_triage")
    root.setLevel(level)
    root.handlers = handlers
    root.propagate = False

    # Capture uvicorn + starlette into the same handlers.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "starlette"):
        lib = logging.getLogger(name)
        lib.handlers = handlers
        lib.setLevel(level)
        lib.propagate = False

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_request_id,
            _drop_pii,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


# --- Public API --------------------------------------------------------------


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a namespaced structlog BoundLogger.

    Call with ``__name__`` from the calling module — the logger auto-prefixes
    with ``supply_chain_triage.`` if the name doesn't already start with it.

    Args:
        name: Module name (``__name__``) or a custom dotted hierarchy.

    Returns:
        ``BoundLogger`` that supports ``.info("event_name", key=value, ...)``
        and emits through the full processor chain + stdlib handlers.
    """
    _configure_once()
    if not name.startswith("supply_chain_triage"):
        name = f"supply_chain_triage.{name}"
    return cast("structlog.stdlib.BoundLogger", structlog.get_logger(name))


def generate_request_id() -> str:
    """Generate a 12-char hex request ID. For middleware use."""
    return uuid.uuid4().hex[:12]


# --- Domain-specific helpers (observability.md §1, §6, §7) -------------------


def log_agent_invocation(
    agent_name: str,
    duration_ms: float,
    *,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    **extra: Any,
) -> None:
    """Record an agent invocation with token-usage attribution (OTel-friendly)."""
    get_logger("agents").info(
        "agent_invoked",
        agent_name=agent_name,
        duration_ms=duration_ms,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        **extra,
    )


def log_tool_call(
    tool_name: str,
    agent_name: str,
    duration_ms: float,
    status: str,
    **extra: Any,
) -> None:
    """Record a tool call with its host agent + completion status."""
    get_logger("tools").info(
        "tool_invoked",
        tool_name=tool_name,
        agent_name=agent_name,
        duration_ms=duration_ms,
        status=status,
        **extra,
    )


def log_firestore_op(
    op: str,
    collection: str,
    doc_count: int,
    duration_ms: float,
    **extra: Any,
) -> None:
    """Record a Firestore op (observability.md §7 — catches N+1 patterns)."""
    get_logger("memory").info(
        "firestore_op",
        op=op,
        collection=collection,
        doc_count=doc_count,
        duration_ms=duration_ms,
        **extra,
    )


_HTTP_SUCCESS_MIN = 200
_HTTP_SUCCESS_MAX_EXCLUSIVE = 300


def log_api_call(
    method: str,
    endpoint: str,
    status_code: int,
    duration_ms: float,
) -> None:
    """Record an API ingress request/response."""
    outcome = "OK" if _HTTP_SUCCESS_MIN <= status_code < _HTTP_SUCCESS_MAX_EXCLUSIVE else "FAIL"
    get_logger("api.access").info(
        "api_call",
        method=method,
        endpoint=endpoint,
        status_code=status_code,
        duration_ms=duration_ms,
        outcome=outcome,
    )


def log_auth_event(
    action: str,
    *,
    uid: str | None = None,
    details: str | None = None,
) -> None:
    """Record an auth lifecycle event (login, claim set, revocation, etc.).

    Args:
        action: The lifecycle action (e.g. ``"login"``, ``"claim_set"``).
            Avoids ``event`` as the kwarg name because structlog reserves
            that for the first positional (the log event name itself).
        uid: Firebase Auth UID. Optional.
        details: Freeform detail string. Optional; kept short — any PII
            must be redacted by the caller.
    """
    get_logger("auth").info(
        "auth_event",
        action=action,
        uid=uid,
        details=details,
    )

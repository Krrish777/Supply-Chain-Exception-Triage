"""Top-level pytest fixtures.

Responsibilities:
- Session-scoped env isolation (stable project ID for emulators).
- Session-scoped Firestore emulator reachability probe — integration tests
  auto-skip when the emulator is not running, so fast unit tests don't require
  Java/firebase CLI / emulator setup.
- Env-var setup (``FIRESTORE_EMULATOR_HOST``, ``FIREBASE_AUTH_EMULATOR_HOST``,
  ``GCLOUD_PROJECT``) runs BEFORE any Firestore / Firebase Admin SDK client is
  imported, per ``.claude/rules/testing.md`` §5.
"""

from __future__ import annotations

import os
import socket
from contextlib import closing
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

_EMULATOR_HOST = "localhost"
_FIRESTORE_PORT = 8080
_AUTH_EMULATOR_PORT = 9099
_TEST_PROJECT_ID = "sct-test"


def _is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    """Return True if something is listening on ``host:port``."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.settimeout(timeout)
        try:
            sock.connect((host, port))
        except OSError:
            return False
        return True


@pytest.fixture(scope="session", autouse=True)
def _set_emulator_env() -> Iterator[None]:
    """Set emulator env vars BEFORE any Firestore/Firebase client is constructed.

    This must run before `firebase_admin.initialize_app()` or
    `google.cloud.firestore.AsyncClient()` is called anywhere in the test run —
    the SDKs read the env at client init, not at call time.

    NEVER set these in production; `FIREBASE_AUTH_EMULATOR_HOST` causes the
    Admin SDK to accept forged tokens (see `.claude/rules/testing.md` §6).
    """
    os.environ.setdefault("FIRESTORE_EMULATOR_HOST", f"{_EMULATOR_HOST}:{_FIRESTORE_PORT}")
    os.environ.setdefault(
        "FIREBASE_AUTH_EMULATOR_HOST",
        f"{_EMULATOR_HOST}:{_AUTH_EMULATOR_PORT}",
    )
    os.environ.setdefault("GCLOUD_PROJECT", _TEST_PROJECT_ID)
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", _TEST_PROJECT_ID)
    return


@pytest.fixture(scope="session")
def firestore_emulator_available() -> bool:
    """Report whether the Firestore emulator is reachable on localhost:8080.

    Tests marked ``@pytest.mark.integration`` that talk to Firestore should
    skip when this returns False — keeps `uv run pytest -m 'not integration'`
    fast and dependency-free.
    """
    return _is_port_open(_EMULATOR_HOST, _FIRESTORE_PORT)


@pytest.fixture
def require_firestore_emulator(firestore_emulator_available: bool) -> None:
    """Per-test guard — skip when the emulator isn't running.

    Use as a dependency in integration tests::

        def test_x(require_firestore_emulator) -> None: ...
    """
    if not firestore_emulator_available:
        pytest.skip(
            "Firestore emulator not reachable at "
            f"{_EMULATOR_HOST}:{_FIRESTORE_PORT}. "
            "Start it via `firebase emulators:start --only firestore,auth`.",
        )


@pytest.fixture
def log_output():  # type: ignore[no-untyped-def]  # structlog.testing.LogCapture has loose typing
    """Capture structured log events for test assertions.

    Usage:

        def test_something(log_output):
            do_the_thing()
            assert any(e["event"] == "expected_event" for e in log_output.entries)

    Per ``.claude/rules/logging.md`` §7. ``structlog.testing.LogCapture`` is
    structlog's canonical test sink — records every event as a dict, making
    assertions trivial and robust against format changes.

    The fixture reconfigures structlog per-test with ONLY the LogCapture
    processor. This cleanly isolates test assertions from handler side
    effects (file rotation, Rich console output). After the test,
    ``utils.logging._configure_once`` is still marked done, so the next
    non-log-capture test re-uses the production config.
    """
    import structlog

    capture = structlog.testing.LogCapture()
    # Save + restore current config so we don't poison sibling tests.
    original_config = structlog.get_config()
    try:
        structlog.configure(processors=[capture])
        yield capture
    finally:
        structlog.configure(**original_config)

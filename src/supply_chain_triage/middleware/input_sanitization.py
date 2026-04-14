"""Input sanitization — strips XSS and control chars, preserves unicode.

Hindi / Hinglish preservation is a hard requirement for the India-first market
(Sprint 0 PRD §2.4, Test 3.3). Any sanitization that strips non-ASCII bytes is
a regression.

The ``sanitize()`` free function is the canonical implementation — it's called
from tools + tests + middleware. The ``InputSanitizationMiddleware`` is a
thin wrapper that applies ``sanitize()`` at the HTTP boundary (stubbed for
Sprint 0; Sprint 4 wires real body rewriting).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
    from starlette.responses import Response


_SCRIPT_TAG_RE = re.compile(
    r"<script\b[^>]*>.*?</script\s*>",
    flags=re.IGNORECASE | re.DOTALL,
)

# Keep \n, \r, \t; strip other control chars < 0x20.
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def sanitize(value: str) -> str:
    r"""Remove ``<script>`` tags and low control chars; preserve unicode.

    Args:
        value: Untrusted input string (may contain Hindi, Hinglish, emoji).

    Returns:
        Sanitized string with XSS script tags removed and control chars
        stripped (preserving ``\n``, ``\r``, ``\t``). Unicode preserved
        byte-for-byte.
    """
    stripped = _SCRIPT_TAG_RE.sub("", value)
    return _CONTROL_CHARS_RE.sub("", stripped)


class InputSanitizationMiddleware(BaseHTTPMiddleware):
    """Stub middleware — Sprint 0 scope.

    Sprint 4 wires real body rewriting using :func:`sanitize` on request bodies.
    For Sprint 0 this is a pass-through so the middleware stack is complete but
    doesn't yet intercept bodies. The ``sanitize()`` function is fully tested
    and available for direct use in tools.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Pass-through in Sprint 0; Sprint 4 adds body sanitization."""
        return await call_next(request)

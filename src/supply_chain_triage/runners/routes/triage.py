"""POST /api/v1/triage — SSE streaming endpoint for the triage pipeline.

Delegates to ``_triage_event_stream`` in the sibling runner and wraps each
yielded frame dict with text/event-stream framing. Auth is a route-level
``Depends(get_current_user)`` that reads claims already validated by
``FirebaseAuthMiddleware`` — the middleware is the perimeter guard, the
dependency is the test-seam (``app.dependency_overrides``).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from supply_chain_triage.modules.triage.models.api_envelopes import (  # noqa: TC001 — FastAPI resolves the body schema at runtime.
    TriagePayload,
)
from supply_chain_triage.runners.triage_runner import _triage_event_stream

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

router = APIRouter(prefix="/api/v1/triage", tags=["triage"])


class FirebaseUser(BaseModel):
    """Subset of Firebase claims lifted into a test-overridable value."""

    model_config = ConfigDict(extra="forbid")

    uid: str
    company_id: str
    email: str | None = None


async def get_current_user(request: Request) -> FirebaseUser:
    """Build a ``FirebaseUser`` from claims already set by ``FirebaseAuthMiddleware``.

    Returning a value here (instead of reading ``request.state`` in the route
    body) gives tests a clean override seam: ``app.dependency_overrides[
    get_current_user] = lambda: FirebaseUser(...)`` per .claude/rules/testing.md §7.
    """
    uid = getattr(request.state, "user_id", None)
    company_id = getattr(request.state, "company_id", None)
    if not uid or not company_id:
        raise HTTPException(status_code=401, detail="unauthenticated")
    return FirebaseUser(
        uid=uid,
        company_id=company_id,
        email=getattr(request.state, "email", None),
    )


CurrentUser = Annotated[FirebaseUser, Depends(get_current_user)]


@router.post("/")
async def triage_exception(
    *,
    current_user: CurrentUser,  # noqa: ARG001 — Day 5 wires correlation/audit_event
    payload: TriagePayload,
) -> StreamingResponse:
    """Stream SSE frames for a single triage run (POST /api/v1/triage)."""
    event_id = (payload.event_id or "").strip() or f"adhoc-{uuid4().hex[:16]}"
    raw_text = payload.raw_text or ""

    async def _framed() -> AsyncIterator[bytes]:
        async for frame in _triage_event_stream(event_id=event_id, raw_text=raw_text):
            event_type = frame["event"]
            data_json = json.dumps(frame["data"], default=str)
            yield f"event: {event_type}\ndata: {data_json}\n\n".encode()

    return StreamingResponse(
        _framed(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Cloud Run / nginx buffer SSE by default — events would batch to the
            # end. Explicit opt-out per docs/research/fastapi-sse-api-design.md.
            "X-Accel-Buffering": "no",
        },
    )

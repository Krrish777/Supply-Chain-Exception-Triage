"""Integration tests I-8..I-11 — SSE streaming runner + POST /api/v1/triage.

I-8 : happy path, NH-48-style event, full frame sequence (needs Gemini + emulator).
I-9 : Rule B short-circuit via raw_text — no Gemini call, ``complete`` frame
      carries ``escalated_to_human_safety`` status.
I-10: client disconnects mid-stream — server-side cleanup fires, no exception
      bubbles up into the test.
I-11: 422 at the Pydantic boundary for empty / whitespace-only payloads.

Auth is overridden via ``app.dependency_overrides[get_current_user]`` per
``.claude/rules/testing.md`` §7. Tests use a minimal FastAPI app that mounts
only the triage router — middleware is exercised separately in middleware
unit tests.
"""

from __future__ import annotations

import os

os.environ.setdefault("GCP_PROJECT_ID", "sct-test")
os.environ.setdefault("FIREBASE_PROJECT_ID", "sct-test")
os.environ.setdefault("SCT_DISABLE_SECRET_MANAGER", "1")

import json
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from supply_chain_triage.runners.routes.triage import (
    FirebaseUser,
    get_current_user,
)
from supply_chain_triage.runners.routes.triage import (
    router as triage_router,
)

_TEST_USER = FirebaseUser(uid="test-user", company_id="acme", email="t@acme.test")


def _build_test_app() -> FastAPI:
    """Minimal app with only the triage router + dep-overridden auth."""
    app = FastAPI()
    app.include_router(triage_router)
    app.dependency_overrides[get_current_user] = lambda: _TEST_USER
    return app


def _parse_sse_stream(text: str) -> list[dict[str, Any]]:
    """Parse a concatenated SSE stream into a list of frame dicts."""
    frames: list[dict[str, Any]] = []
    for block in text.split("\n\n"):
        chunk = block.strip()
        if not chunk:
            continue
        event_type: str | None = None
        data: Any = None
        for line in chunk.split("\n"):
            if line.startswith("event: "):
                event_type = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        if event_type is not None:
            frames.append({"event": event_type, "data": data})
    return frames


# ---------------------------------------------------------------------------
# I-11 — Pydantic boundary validation (no Gemini, no emulator needed)
# ---------------------------------------------------------------------------


class TestI11PayloadValidation:
    """422 before the pipeline even constructs."""

    async def test_empty_body_rejected(self) -> None:
        app = _build_test_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/triage/", json={})
            assert resp.status_code == 422

    async def test_both_fields_empty_rejected(self) -> None:
        app = _build_test_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/triage/", json={"event_id": "", "raw_text": ""})
            assert resp.status_code == 422

    async def test_whitespace_only_rejected(self) -> None:
        app = _build_test_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/triage/", json={"event_id": "   ", "raw_text": "\t\n"}
            )
            assert resp.status_code == 422

    async def test_extra_field_rejected(self) -> None:
        """TriagePayload has extra='forbid' — unknown keys 422."""
        app = _build_test_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/triage/",
                json={"raw_text": "hi", "unexpected": "field"},
            )
            assert resp.status_code == 422


# ---------------------------------------------------------------------------
# I-9 — Rule B short-circuit via SSE (no Gemini — deterministic keyword gate)
# ---------------------------------------------------------------------------


class TestI9RuleBShortCircuit:
    """Safety keyword in raw_text short-circuits before any Gemini call."""

    async def test_rule_b_complete_frame_escalated(self) -> None:
        app = _build_test_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/triage/",
                json={"raw_text": "tanker explosion on NH-48, driver injured"},
            )
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            assert resp.headers.get("x-accel-buffering") == "no"

            frames = _parse_sse_stream(resp.text)
            assert frames, "stream produced no frames"

            # Terminal contract: last frame is done, preceded by complete.
            assert frames[-1]["event"] == "done"
            complete = next(f for f in frames if f["event"] == "complete")
            tri = complete["data"]["triage_result"]
            assert tri["status"] == "escalated_to_human_safety"
            assert tri["classification"]["exception_type"] == "safety_incident"
            assert tri["classification"]["severity"] == "CRITICAL"
            assert tri["impact"] is None


# ---------------------------------------------------------------------------
# I-10 — Client disconnect mid-stream
# ---------------------------------------------------------------------------


class TestI10ClientDisconnect:
    """Client closes the stream early — server cleanup fires without raising."""

    async def test_early_close_does_not_raise(self) -> None:
        app = _build_test_app()
        # Stream + abort after the first chunk — exercises asyncio.CancelledError
        # in the async generator. No exception means cleanup path held.
        async with (
            AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
            client.stream(
                "POST",
                "/api/v1/triage/",
                json={"raw_text": "tanker explosion on NH-48"},
            ) as response,
        ):
            assert response.status_code == 200
            async for _chunk in response.aiter_bytes():
                break  # drop connection after first chunk


# ---------------------------------------------------------------------------
# I-8 — Happy path (needs Gemini + Firestore emulator; seeds like I-1)
# ---------------------------------------------------------------------------


_EVENT_ID_I8 = "EXC-TEST-SSE-I8"
_COMPANY_ID_I8 = "swiftlogix-test-i8"
_RAW_TEXT_I8 = (
    "BlueDart truck BD-MH12-4521 broke down on the Mumbai-Pune Expressway "
    "near Lonavala at 06:30 IST. Driver reports engine failure. 12 packages "
    "onboard for delivery today including 3 high-value B2B shipments for "
    "MegaMart. Mechanic ETA 3 hours. No injuries reported."
)


@pytest.fixture
async def seeded_sse_exception(
    require_firestore_emulator: None,  # fixture guard — value unused
) -> None:
    """Seed the same shape as I-1 so the Impact fetchers have a company + event."""
    from google.cloud.firestore import AsyncClient as FirestoreAsyncClient

    db = FirestoreAsyncClient(project="sct-test")
    await (
        db.collection("companies")
        .document(_COMPANY_ID_I8)
        .set(
            {
                "company_id": _COMPANY_ID_I8,
                "name": "SwiftLogix Test I8",
                "profile_summary": "Small 3PL, Mumbai-Gujarat corridor.",
                "num_trucks": 15,
                "num_employees": 42,
                "regions_of_operation": ["Mumbai"],
                "carriers": ["BlueDart"],
                "customer_portfolio": {
                    "d2c_percentage": 0.3,
                    "b2b_percentage": 0.5,
                    "b2b_enterprise_percentage": 0.2,
                    "top_customers": ["MegaMart"],
                },
                "avg_daily_revenue_inr": 800000,
                "active": True,
            }
        )
    )
    await (
        db.collection("exceptions")
        .document(_EVENT_ID_I8)
        .set(
            {
                "event_id": _EVENT_ID_I8,
                "timestamp": "2026-04-20T06:30:00+00:00",
                "source_channel": "manual_entry",
                "sender": {"name": "Dispatch", "role": "operations"},
                "raw_content": _RAW_TEXT_I8,
                "original_language": None,
                "english_translation": None,
                "media_urls": [],
                "metadata": {"company_id": _COMPANY_ID_I8},
            }
        )
    )

    yield

    await db.collection("companies").document(_COMPANY_ID_I8).delete()
    await db.collection("exceptions").document(_EVENT_ID_I8).delete()


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY"),
    reason="GEMINI_API_KEY required for live SSE happy-path test",
)
async def test_i8_happy_path_frame_sequence(
    seeded_sse_exception: None,  # fixture seeds + cleans up — value unused
) -> None:
    """Happy path: frames arrive in the documented order, ending with done."""
    app = _build_test_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", timeout=60.0
    ) as client:
        resp = await client.post(
            "/api/v1/triage/",
            json={"event_id": _EVENT_ID_I8, "raw_text": _RAW_TEXT_I8},
        )
        assert resp.status_code == 200
        frames = _parse_sse_stream(resp.text)

        types = [f["event"] for f in frames]
        assert types[-1] == "done"
        assert "complete" in types
        assert "agent_started" in types
        # At least one agent must have completed before complete.
        assert types.index("agent_completed") < types.index("complete")
        assert types.index("complete") < types.index("done")

        complete = next(f for f in frames if f["event"] == "complete")
        tri = complete["data"]["triage_result"]
        assert tri["event_id"] == _EVENT_ID_I8
        assert tri["classification"] is not None
        assert tri["classification"]["severity"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}

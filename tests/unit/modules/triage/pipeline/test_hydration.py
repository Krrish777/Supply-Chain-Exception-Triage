"""Unit tests for the deterministic event-hydration callback."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("GCP_PROJECT_ID", "sct-test")
os.environ.setdefault("FIREBASE_PROJECT_ID", "sct-test")
os.environ.setdefault("SCT_DISABLE_SECRET_MANAGER", "1")

from supply_chain_triage.modules.triage.pipeline import hydration as hyd


def _ctx(initial: dict | None = None) -> MagicMock:
    """Build a mock callback context with a real dict for state."""
    ctx = MagicMock()
    ctx.state = dict(initial or {})
    return ctx


@pytest.fixture
def patch_lookups(monkeypatch):
    """Patch the two lookup helpers; tests configure return values per-case."""
    get_event = AsyncMock()
    get_company = AsyncMock()
    monkeypatch.setattr(hyd, "get_exception_event", get_event)
    monkeypatch.setattr(hyd, "get_company_profile", get_company)
    return get_event, get_company


class TestPathAStructuredEventId:
    async def test_success_hydrates_event_and_company(self, patch_lookups):
        get_event, get_company = patch_lookups
        get_event.return_value = {
            "status": "success",
            "data": {
                "raw_content": "Chemical tanker overturned on NH8.",
                "metadata": {"company_id": "swiftlogix-001"},
            },
        }
        get_company.return_value = {
            "status": "success",
            "data": {"name": "SwiftLogix"},
            "markdown": "## Business Context\n- Company: SwiftLogix",
        }
        ctx = _ctx({"triage:event_id": "EXC-2026-0004", "triage:event_raw_text": ""})

        await hyd._hydrate_event(ctx)

        assert ctx.state["triage:event_raw_content"] == "Chemical tanker overturned on NH8."
        # Re-seed: Rule B should now see the real text.
        assert ctx.state["triage:event_raw_text"] == "Chemical tanker overturned on NH8."
        assert ctx.state["triage:event_metadata"] == {"company_id": "swiftlogix-001"}
        assert ctx.state["triage:company_id"] == "swiftlogix-001"
        assert "SwiftLogix" in ctx.state["triage:company_markdown"]
        assert "triage:hydration_error" not in ctx.state
        get_event.assert_awaited_once()
        get_company.assert_awaited_once()

    async def test_event_not_found_records_error_and_continues(self, patch_lookups):
        get_event, get_company = patch_lookups
        get_event.return_value = {
            "status": "error",
            "error_message": "Exception event 'EXC-2026-0099' not found",
        }
        ctx = _ctx({"triage:event_id": "EXC-2026-0099", "triage:event_raw_text": "fallback text"})

        await hyd._hydrate_event(ctx)

        assert "not found" in ctx.state["triage:hydration_error"]
        assert ctx.state["triage:event_raw_content"] == "fallback text"
        # No company_id from event metadata, no auth claim → no company lookup attempted.
        get_company.assert_not_awaited()

    async def test_event_metadata_company_takes_precedence_over_auth(self, patch_lookups):
        get_event, get_company = patch_lookups
        get_event.return_value = {
            "status": "success",
            "data": {
                "raw_content": "Routine breakdown.",
                "metadata": {"company_id": "from-event"},
            },
        }
        get_company.return_value = {
            "status": "success",
            "data": {},
            "markdown": "## Business Context",
        }
        ctx = _ctx(
            {
                "triage:event_id": "EXC-2026-0001",
                "triage:auth_company_id": "from-auth",
            }
        )

        await hyd._hydrate_event(ctx)

        assert ctx.state["triage:company_id"] == "from-event"
        get_company.assert_awaited_once_with("from-event", ctx)


class TestPathBNaturalLanguage:
    async def test_no_event_id_copies_raw_text(self, patch_lookups):
        get_event, get_company = patch_lookups
        ctx = _ctx({"triage:event_id": "", "triage:event_raw_text": "Trucks stuck on NH8."})

        await hyd._hydrate_event(ctx)

        assert ctx.state["triage:event_raw_content"] == "Trucks stuck on NH8."
        get_event.assert_not_awaited()
        get_company.assert_not_awaited()

    async def test_adhoc_id_treated_as_path_b(self, patch_lookups):
        get_event, _ = patch_lookups
        ctx = _ctx(
            {
                "triage:event_id": "adhoc-abcd1234",
                "triage:event_raw_text": "Chemical spill on highway.",
            }
        )

        await hyd._hydrate_event(ctx)

        assert ctx.state["triage:event_raw_content"] == "Chemical spill on highway."
        get_event.assert_not_awaited()

    async def test_auth_company_id_drives_company_hydration(self, patch_lookups):
        _, get_company = patch_lookups
        get_company.return_value = {
            "status": "success",
            "data": {"name": "SwiftLogix"},
            "markdown": "## Business Context\n- Company: SwiftLogix",
        }
        ctx = _ctx(
            {
                "triage:event_id": "",
                "triage:event_raw_text": "Routine delay.",
                "triage:auth_company_id": "swiftlogix-001",
            }
        )

        await hyd._hydrate_event(ctx)

        assert ctx.state["triage:company_id"] == "swiftlogix-001"
        assert "SwiftLogix" in ctx.state["triage:company_markdown"]


class TestCompanyHydrationFailure:
    async def test_company_not_found_records_error(self, patch_lookups):
        _, get_company = patch_lookups
        get_company.return_value = {
            "status": "error",
            "error_message": "Company 'missing' not found",
        }
        ctx = _ctx(
            {
                "triage:event_id": "",
                "triage:event_raw_text": "Some text.",
                "triage:auth_company_id": "missing",
            }
        )

        await hyd._hydrate_event(ctx)

        assert ctx.state["triage:hydration_error"] == "Company 'missing' not found"
        assert "triage:company_markdown" not in ctx.state

    async def test_event_error_preserved_when_company_also_fails(self, patch_lookups):
        get_event, get_company = patch_lookups
        get_event.return_value = {"status": "error", "error_message": "event boom"}
        get_company.return_value = {"status": "error", "error_message": "company boom"}
        ctx = _ctx(
            {
                "triage:event_id": "EXC-2026-0001",
                "triage:event_raw_text": "fallback",
                "triage:auth_company_id": "swiftlogix-001",
            }
        )

        await hyd._hydrate_event(ctx)

        # Event-side error wins (set first via setdefault discipline).
        assert ctx.state["triage:hydration_error"] == "event boom"

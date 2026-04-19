"""Unit tests for shared lookup tools (get_exception_event, get_company_profile)."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("GCP_PROJECT_ID", "sct-test")
os.environ.setdefault("FIREBASE_PROJECT_ID", "sct-test")
os.environ.setdefault("SCT_DISABLE_SECRET_MANAGER", "1")

from supply_chain_triage.modules.triage.tools.lookup import (
    get_company_profile,
    get_exception_event,
)


def _tool_context() -> MagicMock:
    ctx = MagicMock()
    ctx.state = {}
    return ctx


def _mock_doc(data: dict | None, exists: bool = True) -> MagicMock:
    doc = MagicMock()
    doc.exists = exists
    doc.id = data.get("event_id", "test-id") if data else "test-id"
    doc.to_dict.return_value = data
    return doc


SAMPLE_EXCEPTION = {
    "event_id": "EXC-001",
    "timestamp": "2026-04-16T06:30:00+00:00",
    "source_channel": "manual_entry",
    "sender": {"name": "Test", "role": "ops"},
    "raw_content": "Test exception content",
    "original_language": None,
    "english_translation": None,
    "media_urls": [],
    "metadata": {"company_id": "comp-001"},
}

SAMPLE_COMPANY = {
    "company_id": "comp-001",
    "name": "TestCo",
    "profile_summary": "Test company",
    "num_trucks": 5,
    "num_employees": 10,
    "regions_of_operation": ["Mumbai"],
    "carriers": ["BlueDart"],
    "customer_portfolio": {
        "d2c_percentage": 0.5,
        "b2b_percentage": 0.3,
        "b2b_enterprise_percentage": 0.2,
        "top_customers": ["Acme"],
    },
    "avg_daily_revenue_inr": 500000,
    "active": True,
}

_PATCH_TARGET = "supply_chain_triage.modules.triage.tools.lookup.get_firestore_client"


def _mock_firestore_db(doc_mock: AsyncMock) -> MagicMock:
    """Build a mock Firestore client with sync collection/document, async get."""
    db = MagicMock()
    doc_ref = MagicMock()
    doc_ref.get = AsyncMock(return_value=doc_mock)
    db.collection.return_value.document.return_value = doc_ref
    return db


class TestGetExceptionEvent:
    @pytest.fixture(autouse=True)
    def _patch_firestore(self):
        with patch(_PATCH_TARGET) as mock_client:
            self.mock_client = mock_client
            yield

    async def test_success_returns_data(self):
        doc = _mock_doc(SAMPLE_EXCEPTION)
        self.mock_client.return_value = _mock_firestore_db(doc)
        ctx = _tool_context()

        result = await get_exception_event("EXC-001", ctx)

        assert result["status"] == "success"
        assert result["data"]["event_id"] == "EXC-001"
        assert result["data"]["raw_content"] == "Test exception content"

    async def test_not_found_returns_error(self):
        doc = _mock_doc(None, exists=False)
        self.mock_client.return_value = _mock_firestore_db(doc)
        ctx = _tool_context()

        result = await get_exception_event("MISSING", ctx)

        assert result["status"] == "error"
        assert "not found" in result["error_message"]

    async def test_firestore_error_returns_error(self):
        db = MagicMock()
        doc_ref = MagicMock()
        doc_ref.get = AsyncMock(side_effect=ConnectionError("emulator down"))
        db.collection.return_value.document.return_value = doc_ref
        self.mock_client.return_value = db
        ctx = _tool_context()

        result = await get_exception_event("EXC-001", ctx)

        assert result["status"] == "error"
        assert "ConnectionError" in result["error_message"]

    async def test_cache_hit_skips_firestore(self):
        self.mock_client.return_value = MagicMock()
        ctx = _tool_context()
        cached_data = {"event_id": "EXC-001", "cached": True}
        ctx.state["cache:exception:EXC-001"] = cached_data

        result = await get_exception_event("EXC-001", ctx)

        assert result["status"] == "success"
        assert result["data"]["cached"] is True
        self.mock_client.return_value.collection.assert_not_called()

    async def test_success_populates_cache(self):
        doc = _mock_doc(SAMPLE_EXCEPTION)
        self.mock_client.return_value = _mock_firestore_db(doc)
        ctx = _tool_context()

        await get_exception_event("EXC-001", ctx)

        assert "cache:exception:EXC-001" in ctx.state


class TestGetCompanyProfile:
    @pytest.fixture(autouse=True)
    def _patch_firestore(self):
        with patch(_PATCH_TARGET) as mock_client:
            self.mock_client = mock_client
            yield

    async def test_success_returns_data_and_markdown(self):
        doc = _mock_doc(SAMPLE_COMPANY)
        doc.id = "comp-001"
        self.mock_client.return_value = _mock_firestore_db(doc)
        ctx = _tool_context()

        result = await get_company_profile("comp-001", ctx)

        assert result["status"] == "success"
        assert result["data"]["name"] == "TestCo"
        assert "## Business Context" in result["markdown"]

    async def test_not_found_returns_error(self):
        doc = _mock_doc(None, exists=False)
        self.mock_client.return_value = _mock_firestore_db(doc)
        ctx = _tool_context()

        result = await get_company_profile("MISSING", ctx)

        assert result["status"] == "error"
        assert "not found" in result["error_message"]

    async def test_cache_hit_skips_firestore(self):
        self.mock_client.return_value = MagicMock()
        ctx = _tool_context()
        ctx.state["cache:company:comp-001"] = {
            "data": {"name": "Cached"},
            "markdown": "## Cached",
        }

        result = await get_company_profile("comp-001", ctx)

        assert result["status"] == "success"
        assert result["data"]["name"] == "Cached"
        self.mock_client.return_value.collection.assert_not_called()

    async def test_success_populates_cache(self):
        doc = _mock_doc(SAMPLE_COMPANY)
        doc.id = "comp-001"
        self.mock_client.return_value = _mock_firestore_db(doc)
        ctx = _tool_context()

        await get_company_profile("comp-001", ctx)

        assert "cache:company:comp-001" in ctx.state

"""Unit tests for impact-agent tools (Firestore lookups and financial impact calculation)."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("GCP_PROJECT_ID", "sct-test")
os.environ.setdefault("FIREBASE_PROJECT_ID", "sct-test")
os.environ.setdefault("SCT_DISABLE_SECRET_MANAGER", "1")

from supply_chain_triage.modules.triage.agents.impact.tools import (
    calculate_financial_impact,
    get_affected_shipments,
    get_customer_profile,
    get_route_and_hub_status,
    get_shipment_details,
)

_PATCH_TARGET = "supply_chain_triage.modules.triage.agents.impact.tools.get_firestore_client"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool_context(**state_overrides):
    ctx = MagicMock()
    ctx.state = dict(state_overrides)
    return ctx


def _make_doc(doc_id: str, data: dict | None, exists: bool = True) -> MagicMock:
    doc = MagicMock()
    doc.id = doc_id
    doc.exists = exists
    doc.to_dict.return_value = data if exists else None
    return doc


async def _async_iter(items):
    for item in items:
        yield item


def _make_firestore_db(doc_mock: MagicMock) -> MagicMock:
    db = MagicMock()
    doc_ref = MagicMock()
    doc_ref.get = AsyncMock(return_value=doc_mock)
    db.collection.return_value.document.return_value = doc_ref
    return db


# ---------------------------------------------------------------------------
# get_affected_shipments
# ---------------------------------------------------------------------------


class TestGetAffectedShipments:
    @pytest.fixture(autouse=True)
    def _patch_firestore(self):
        with patch(_PATCH_TARGET) as mock_client:
            self.mock_client = mock_client
            yield

    async def test_success_returns_shipments(self):
        doc1 = _make_doc(
            "ship-001",
            {
                "customer_id": "cust-1",
                "value_inr": 100000,
                "destination": "Mumbai",
                "deadline": "2026-04-18T10:00:00+00:00",
                "vehicle_id": "MH-04-AB-1234",
                "route_id": "route-001",
            },
        )
        doc2 = _make_doc(
            "ship-002",
            {
                "customer_id": "cust-2",
                "value_inr": 200000,
                "destination": "Delhi",
                "deadline": "2026-04-19T10:00:00+00:00",
                "vehicle_id": "MH-04-AB-1234",
                "route_id": "route-001",
            },
        )

        db = MagicMock()
        query = MagicMock()
        query.where.return_value = query
        query.stream.return_value = _async_iter([doc1, doc2])
        db.collection.return_value.where.return_value = query
        self.mock_client.return_value = db

        ctx = _make_tool_context()
        result = await get_affected_shipments("vehicle_id", "MH-04-AB-1234", ctx)

        assert result["status"] == "success"
        assert result["data"]["count"] == 2
        shipments = result["data"]["shipments"]
        assert len(shipments) == 2
        assert shipments[0]["shipment_id"] == "ship-001"
        assert shipments[1]["shipment_id"] == "ship-002"
        assert shipments[0]["customer_id"] == "cust-1"

    async def test_invalid_scope_type_returns_error(self):
        ctx = _make_tool_context()
        result = await get_affected_shipments("invalid", "some-value", ctx)

        assert result["status"] == "error"
        assert "Invalid scope_type" in result["error_message"]
        # Firestore must not have been called
        self.mock_client.assert_not_called()

    async def test_no_shipments_found(self):
        db = MagicMock()
        query = MagicMock()
        query.where.return_value = query
        query.stream.return_value = _async_iter([])
        db.collection.return_value.where.return_value = query
        self.mock_client.return_value = db

        ctx = _make_tool_context()
        result = await get_affected_shipments("route_id", "route-999", ctx)

        assert result["status"] == "success"
        assert result["data"]["count"] == 0
        assert result["data"]["shipments"] == []

    async def test_cache_hit_skips_firestore(self):
        cache_key = "cache:shipments:vehicle_id:MH-04-XX-0001"
        cached_data = {"shipments": [{"shipment_id": "cached-ship"}], "count": 1}
        ctx = _make_tool_context(**{cache_key: cached_data})

        result = await get_affected_shipments("vehicle_id", "MH-04-XX-0001", ctx)

        assert result["status"] == "success"
        assert result["data"]["shipments"][0]["shipment_id"] == "cached-ship"
        self.mock_client.assert_not_called()

    async def test_firestore_error_returns_error(self):
        db = MagicMock()
        query = MagicMock()
        query.where.return_value = query
        query.stream.side_effect = ConnectionError("emulator down")
        db.collection.return_value.where.return_value = query
        self.mock_client.return_value = db

        ctx = _make_tool_context()
        result = await get_affected_shipments("region", "mumbai", ctx)

        assert result["status"] == "error"
        assert "ConnectionError" in result["error_message"]


# ---------------------------------------------------------------------------
# get_shipment_details
# ---------------------------------------------------------------------------


class TestGetShipmentDetails:
    @pytest.fixture(autouse=True)
    def _patch_firestore(self):
        with patch(_PATCH_TARGET) as mock_client:
            self.mock_client = mock_client
            yield

    async def test_success_returns_full_doc(self):
        data = {
            "customer_id": "cust-001",
            "value_inr": 500000,
            "destination": "Chennai",
            "status": "in_transit",
        }
        doc = _make_doc("ship-123", data)
        self.mock_client.return_value = _make_firestore_db(doc)

        ctx = _make_tool_context()
        result = await get_shipment_details("ship-123", ctx)

        assert result["status"] == "success"
        assert result["data"]["shipment_id"] == "ship-123"
        assert result["data"]["customer_id"] == "cust-001"
        assert result["data"]["value_inr"] == 500000

    async def test_not_found_returns_error(self):
        doc = _make_doc("ship-missing", None, exists=False)
        self.mock_client.return_value = _make_firestore_db(doc)

        ctx = _make_tool_context()
        result = await get_shipment_details("ship-missing", ctx)

        assert result["status"] == "error"
        assert "not found" in result["error_message"]

    async def test_cache_hit_skips_firestore(self):
        cache_key = "cache:shipment:ship-cached"
        cached = {"shipment_id": "ship-cached", "value_inr": 999}
        ctx = _make_tool_context(**{cache_key: cached})

        result = await get_shipment_details("ship-cached", ctx)

        assert result["status"] == "success"
        assert result["data"]["value_inr"] == 999
        self.mock_client.assert_not_called()

    async def test_populates_cache_on_success(self):
        data = {"customer_id": "cust-001", "value_inr": 100000}
        doc = _make_doc("ship-new", data)
        self.mock_client.return_value = _make_firestore_db(doc)

        ctx = _make_tool_context()
        await get_shipment_details("ship-new", ctx)

        assert "cache:shipment:ship-new" in ctx.state

    async def test_firestore_error_returns_error(self):
        db = MagicMock()
        doc_ref = MagicMock()
        doc_ref.get = AsyncMock(side_effect=TimeoutError("timeout"))
        db.collection.return_value.document.return_value = doc_ref
        self.mock_client.return_value = db

        ctx = _make_tool_context()
        result = await get_shipment_details("ship-timeout", ctx)

        assert result["status"] == "error"
        assert "TimeoutError" in result["error_message"]


# ---------------------------------------------------------------------------
# get_customer_profile
# ---------------------------------------------------------------------------


class TestGetCustomerProfile:
    @pytest.fixture(autouse=True)
    def _patch_firestore(self):
        with patch(_PATCH_TARGET) as mock_client:
            self.mock_client = mock_client
            yield

    async def test_success_returns_profile(self):
        data = {
            "name": "Acme Corp",
            "tier": "high_value",
            "ltv_inr": 5000000,
            "churn_risk": "LOW",
        }
        doc = _make_doc("cust-001", data)
        self.mock_client.return_value = _make_firestore_db(doc)

        ctx = _make_tool_context()
        result = await get_customer_profile("cust-001", ctx)

        assert result["status"] == "success"
        assert result["data"]["customer_id"] == "cust-001"
        assert result["data"]["name"] == "Acme Corp"
        assert result["data"]["tier"] == "high_value"

    async def test_not_found_returns_error(self):
        doc = _make_doc("cust-missing", None, exists=False)
        self.mock_client.return_value = _make_firestore_db(doc)

        ctx = _make_tool_context()
        result = await get_customer_profile("cust-missing", ctx)

        assert result["status"] == "error"
        assert "not found" in result["error_message"]

    async def test_cache_hit_skips_firestore(self):
        cache_key = "cache:customer:cust-cached"
        cached = {"customer_id": "cust-cached", "name": "Cached Corp"}
        ctx = _make_tool_context(**{cache_key: cached})

        result = await get_customer_profile("cust-cached", ctx)

        assert result["status"] == "success"
        assert result["data"]["name"] == "Cached Corp"
        self.mock_client.assert_not_called()

    async def test_populates_cache_on_success(self):
        data = {"name": "NewCo", "ltv_inr": 1000000}
        doc = _make_doc("cust-new", data)
        self.mock_client.return_value = _make_firestore_db(doc)

        ctx = _make_tool_context()
        await get_customer_profile("cust-new", ctx)

        assert "cache:customer:cust-new" in ctx.state

    async def test_firestore_error_returns_error(self):
        db = MagicMock()
        doc_ref = MagicMock()
        doc_ref.get = AsyncMock(side_effect=ConnectionError("offline"))
        db.collection.return_value.document.return_value = doc_ref
        self.mock_client.return_value = db

        ctx = _make_tool_context()
        result = await get_customer_profile("cust-err", ctx)

        assert result["status"] == "error"
        assert "ConnectionError" in result["error_message"]


# ---------------------------------------------------------------------------
# get_route_and_hub_status
# ---------------------------------------------------------------------------


class TestGetRouteAndHubStatus:
    @pytest.fixture(autouse=True)
    def _patch_firestore(self):
        with patch(_PATCH_TARGET) as mock_client:
            self.mock_client = mock_client
            yield

    def _build_db_with_route_and_hubs(
        self,
        route_id: str,
        route_data: dict,
        hub_docs: list[MagicMock],
    ) -> MagicMock:
        route_doc = _make_doc(route_id, route_data)
        db = MagicMock()

        # We need the route doc on first get, then hub docs by ID.
        # Use a side_effect list for sequential calls.
        call_results = [route_doc, *hub_docs]

        doc_ref = MagicMock()
        doc_ref.get = AsyncMock(side_effect=call_results)
        db.collection.return_value.document.return_value = doc_ref
        return db

    async def test_success_returns_route_and_hubs(self):
        route_data = {
            "name": "Mumbai-Delhi",
            "legs": [
                {"origin_hub": "hub-mum", "destination_hub": "hub-del"},
            ],
        }
        hub_mum = _make_doc("hub-mum", {"name": "Mumbai Hub", "capacity": 100})
        hub_del = _make_doc("hub-del", {"name": "Delhi Hub", "capacity": 80})

        db = self._build_db_with_route_and_hubs("route-001", route_data, [hub_mum, hub_del])
        self.mock_client.return_value = db

        ctx = _make_tool_context()
        result = await get_route_and_hub_status("route-001", ctx)

        assert result["status"] == "success"
        assert result["data"]["route"]["route_id"] == "route-001"
        assert result["data"]["route"]["name"] == "Mumbai-Delhi"
        assert len(result["data"]["hubs"]) == 2

    async def test_route_not_found(self):
        doc = _make_doc("route-missing", None, exists=False)
        self.mock_client.return_value = _make_firestore_db(doc)

        ctx = _make_tool_context()
        result = await get_route_and_hub_status("route-missing", ctx)

        assert result["status"] == "error"
        assert "not found" in result["error_message"]

    async def test_cache_hit_skips_firestore(self):
        cache_key = "cache:route:route-cached"
        cached = {"route": {"route_id": "route-cached"}, "hubs": []}
        ctx = _make_tool_context(**{cache_key: cached})

        result = await get_route_and_hub_status("route-cached", ctx)

        assert result["status"] == "success"
        assert result["data"]["route"]["route_id"] == "route-cached"
        self.mock_client.assert_not_called()

    async def test_populates_cache_on_success(self):
        route_data = {"name": "Test Route", "legs": []}
        route_doc = _make_doc("route-new", route_data)
        db = _make_firestore_db(route_doc)
        self.mock_client.return_value = db

        ctx = _make_tool_context()
        await get_route_and_hub_status("route-new", ctx)

        assert "cache:route:route-new" in ctx.state

    async def test_firestore_error_returns_error(self):
        db = MagicMock()
        doc_ref = MagicMock()
        doc_ref.get = AsyncMock(side_effect=RuntimeError("db unavailable"))
        db.collection.return_value.document.return_value = doc_ref
        self.mock_client.return_value = db

        ctx = _make_tool_context()
        result = await get_route_and_hub_status("route-err", ctx)

        assert result["status"] == "error"
        assert "RuntimeError" in result["error_message"]


# ---------------------------------------------------------------------------
# calculate_financial_impact
# ---------------------------------------------------------------------------


class TestCalculateFinancialImpact:
    """calculate_financial_impact is a sync, pure-computation tool."""

    def _call(self, **overrides):
        defaults = {
            "shipment_value_inr": 100_000,
            "penalty_per_hour_inr": 1_000,
            "max_penalty_inr": 10_000,
            "estimated_delay_hours": 5.0,
            "rerouting_distance_km": 100.0,
            "holding_days": 2.0,
            "container_count": 3,
            "customer_ltv_inr": 1_000_000,
            "churn_risk_score": 0.5,
            "tool_context": _make_tool_context(),
        }
        defaults.update(overrides)
        return calculate_financial_impact(**defaults)

    def test_basic_calculation(self):
        result = self._call(
            shipment_value_inr=100_000,
            penalty_per_hour_inr=1_000,
            max_penalty_inr=10_000,
            estimated_delay_hours=5.0,
            rerouting_distance_km=100.0,
            holding_days=2.0,
            container_count=3,
            customer_ltv_inr=1_000_000,
            churn_risk_score=0.5,
        )

        assert result["status"] == "success"
        data = result["data"]
        # penalty = min(1000 * 5, 10000) = 5000
        assert data["penalty_exposure_inr"] == 5_000
        # rerouting = 100 * 15 = 1500
        assert data["rerouting_cost_inr"] == 1_500
        # holding = 2 * 500 * 3 = 3000
        assert data["holding_cost_inr"] == 3_000
        # opportunity = 1000000 * 0.5 * 0.10 = 50000
        assert data["opportunity_cost_inr"] == 50_000
        # total = 100000 + 5000 + 1500 + 3000 + 50000 = 159500
        assert data["total_impact_inr"] == 159_500
        assert data["shipment_value_inr"] == 100_000
        assert "breakdown_notes" in data

    def test_penalty_capped_at_max(self):
        # 2000 * 20 = 40000, but max is 15000 — must be capped
        result = self._call(
            penalty_per_hour_inr=2_000,
            max_penalty_inr=15_000,
            estimated_delay_hours=20.0,
            rerouting_distance_km=0.0,
            holding_days=0.0,
            container_count=0,
            customer_ltv_inr=0,
            churn_risk_score=0.0,
            shipment_value_inr=0,
        )

        assert result["status"] == "success"
        assert result["data"]["penalty_exposure_inr"] == 15_000

    def test_zero_values(self):
        result = self._call(
            shipment_value_inr=500_000,
            penalty_per_hour_inr=0,
            max_penalty_inr=0,
            estimated_delay_hours=0.0,
            rerouting_distance_km=0.0,
            holding_days=0.0,
            container_count=0,
            customer_ltv_inr=0,
            churn_risk_score=0.0,
        )

        assert result["status"] == "success"
        data = result["data"]
        assert data["penalty_exposure_inr"] == 0
        assert data["rerouting_cost_inr"] == 0
        assert data["holding_cost_inr"] == 0
        assert data["opportunity_cost_inr"] == 0
        assert data["total_impact_inr"] == 500_000

    def test_high_churn_risk_opportunity_cost(self):
        # churn_risk_score=1.0, LTV=2_000_000 → opportunity = 2_000_000 * 1.0 * 0.10 = 200_000
        result = self._call(
            shipment_value_inr=0,
            penalty_per_hour_inr=0,
            max_penalty_inr=0,
            estimated_delay_hours=0.0,
            rerouting_distance_km=0.0,
            holding_days=0.0,
            container_count=0,
            customer_ltv_inr=2_000_000,
            churn_risk_score=1.0,
        )

        assert result["status"] == "success"
        assert result["data"]["opportunity_cost_inr"] == 200_000
        assert result["data"]["total_impact_inr"] == 200_000

    def test_breakdown_notes_present_and_non_empty(self):
        result = self._call()
        assert result["status"] == "success"
        notes = result["data"]["breakdown_notes"]
        assert isinstance(notes, str)
        assert len(notes) > 0
        assert "INR" in notes

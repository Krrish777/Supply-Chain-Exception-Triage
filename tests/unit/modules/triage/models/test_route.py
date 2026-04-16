"""Tests for route and hub models used by the Impact Agent."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from supply_chain_triage.modules.triage.models.route import (
    HubCapacityWindow,
    HubStatus,
    RouteDefinition,
    RouteLeg,
)

# ---------------------------------------------------------------------------
# RouteLeg
# ---------------------------------------------------------------------------


class TestRouteLeg:
    def test_valid_construction(self) -> None:
        leg = RouteLeg(
            leg_number=1,
            origin_hub="Mumbai",
            destination_hub="Pune",
            distance_km=148.5,
            estimated_hours=3.0,
        )
        assert leg.leg_number == 1
        assert leg.origin_hub == "Mumbai"
        assert leg.destination_hub == "Pune"
        assert leg.distance_km == 148.5
        assert leg.estimated_hours == 3.0

    def test_rejects_leg_number_zero(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            RouteLeg(
                leg_number=0,
                origin_hub="Mumbai",
                destination_hub="Pune",
                distance_km=148.5,
                estimated_hours=3.0,
            )
        assert "leg_number" in str(excinfo.value)

    def test_rejects_leg_number_negative(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            RouteLeg(
                leg_number=-1,
                origin_hub="Mumbai",
                destination_hub="Pune",
                distance_km=148.5,
                estimated_hours=3.0,
            )
        assert "leg_number" in str(excinfo.value)

    def test_rejects_distance_km_zero(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            RouteLeg(
                leg_number=1,
                origin_hub="Mumbai",
                destination_hub="Pune",
                distance_km=0,
                estimated_hours=3.0,
            )
        assert "distance_km" in str(excinfo.value)

    def test_rejects_distance_km_negative(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            RouteLeg(
                leg_number=1,
                origin_hub="Mumbai",
                destination_hub="Pune",
                distance_km=-10.0,
                estimated_hours=3.0,
            )
        assert "distance_km" in str(excinfo.value)

    def test_rejects_estimated_hours_zero(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            RouteLeg(
                leg_number=1,
                origin_hub="Mumbai",
                destination_hub="Pune",
                distance_km=148.5,
                estimated_hours=0,
            )
        assert "estimated_hours" in str(excinfo.value)

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            RouteLeg(
                leg_number=1,
                origin_hub="Mumbai",
                destination_hub="Pune",
                distance_km=148.5,
                estimated_hours=3.0,
                unexpected_field="value",
            )


# ---------------------------------------------------------------------------
# RouteDefinition
# ---------------------------------------------------------------------------


class TestRouteDefinition:
    def _make_leg(self, n: int = 1) -> RouteLeg:
        return RouteLeg(
            leg_number=n,
            origin_hub=f"Hub{n}",
            destination_hub=f"Hub{n + 1}",
            distance_km=100.0 * n,
            estimated_hours=2.0 * n,
        )

    def test_valid_with_multiple_legs(self) -> None:
        legs = [self._make_leg(1), self._make_leg(2)]
        route = RouteDefinition(
            route_id="ROUTE-001",
            corridor_name="Mumbai-Delhi NH-48",
            legs=legs,
            total_distance_km=1400.0,
        )
        assert route.route_id == "ROUTE-001"
        assert len(route.legs) == 2
        assert route.total_distance_km == 1400.0

    def test_valid_with_empty_legs(self) -> None:
        route = RouteDefinition(
            route_id="ROUTE-002",
            corridor_name="Test Corridor",
            legs=[],
            total_distance_km=500.0,
        )
        assert route.legs == []

    def test_rejects_empty_route_id(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            RouteDefinition(
                route_id="",
                corridor_name="Test",
                legs=[],
                total_distance_km=500.0,
            )
        assert "route_id" in str(excinfo.value)

    def test_rejects_total_distance_zero(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            RouteDefinition(
                route_id="ROUTE-003",
                corridor_name="Test",
                legs=[],
                total_distance_km=0,
            )
        assert "total_distance_km" in str(excinfo.value)


# ---------------------------------------------------------------------------
# HubCapacityWindow
# ---------------------------------------------------------------------------


class TestHubCapacityWindow:
    def test_valid_construction(self) -> None:
        window = HubCapacityWindow(
            window_label="next_24h",
            utilization_pct=75.0,
            pending_shipments=42,
        )
        assert window.window_label == "next_24h"
        assert window.utilization_pct == 75.0
        assert window.pending_shipments == 42

    def test_utilization_boundary_zero(self) -> None:
        window = HubCapacityWindow(
            window_label="next_24h",
            utilization_pct=0.0,
            pending_shipments=0,
        )
        assert window.utilization_pct == 0.0

    def test_utilization_boundary_hundred(self) -> None:
        window = HubCapacityWindow(
            window_label="next_24h",
            utilization_pct=100.0,
            pending_shipments=10,
        )
        assert window.utilization_pct == 100.0

    def test_rejects_utilization_above_100(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            HubCapacityWindow(
                window_label="next_24h",
                utilization_pct=100.1,
                pending_shipments=10,
            )
        assert "utilization_pct" in str(excinfo.value)

    def test_rejects_negative_utilization(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            HubCapacityWindow(
                window_label="next_24h",
                utilization_pct=-1.0,
                pending_shipments=10,
            )
        assert "utilization_pct" in str(excinfo.value)

    def test_rejects_negative_pending_shipments(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            HubCapacityWindow(
                window_label="next_24h",
                utilization_pct=50.0,
                pending_shipments=-1,
            )
        assert "pending_shipments" in str(excinfo.value)

    def test_rejects_invalid_window_label(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            HubCapacityWindow(
                window_label="invalid_window",
                utilization_pct=50.0,
                pending_shipments=5,
            )
        assert "window_label" in str(excinfo.value)


# ---------------------------------------------------------------------------
# HubStatus
# ---------------------------------------------------------------------------


def _valid_hub_status(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "hub_id": "HUB-MUM-01",
        "hub_name": "Mumbai JNPT Gateway",
        "city": "Mumbai",
        "hub_type": "major",
        "capacity_containers_per_day": 500,
        "current_utilization_pct": 82.0,
        "congestion_level": "HIGH",
        "time_windows": [],
    }
    base.update(overrides)
    return base


class TestHubStatus:
    def test_valid_construction_all_fields(self) -> None:
        windows = [
            HubCapacityWindow(window_label="next_24h", utilization_pct=85.0, pending_shipments=20),
            HubCapacityWindow(window_label="24_to_48h", utilization_pct=70.0, pending_shipments=15),
        ]
        hub = HubStatus(**_valid_hub_status(time_windows=windows))
        assert hub.hub_id == "HUB-MUM-01"
        assert hub.hub_type == "major"
        assert hub.congestion_level == "HIGH"
        assert len(hub.time_windows) == 2

    def test_time_windows_defaults_to_empty_list(self) -> None:
        data = _valid_hub_status()
        data.pop("time_windows")
        hub = HubStatus(**data)
        assert hub.time_windows == []

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            HubStatus(**_valid_hub_status(unexpected_key="boom"))

    def test_rejects_invalid_hub_type(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            HubStatus(**_valid_hub_status(hub_type="warehouse"))
        assert "hub_type" in str(excinfo.value)

    def test_all_valid_hub_types(self) -> None:
        for hub_type in ("major", "distribution", "transit", "regional"):
            hub = HubStatus(**_valid_hub_status(hub_type=hub_type))
            assert hub.hub_type == hub_type

    def test_rejects_invalid_congestion_level(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            HubStatus(**_valid_hub_status(congestion_level="EXTREME"))
        assert "congestion_level" in str(excinfo.value)

    def test_all_valid_congestion_levels(self) -> None:
        for level in ("LOW", "MODERATE", "HIGH", "CRITICAL"):
            hub = HubStatus(**_valid_hub_status(congestion_level=level))
            assert hub.congestion_level == level

    def test_rejects_capacity_zero(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            HubStatus(**_valid_hub_status(capacity_containers_per_day=0))
        assert "capacity_containers_per_day" in str(excinfo.value)

    def test_rejects_empty_hub_id(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            HubStatus(**_valid_hub_status(hub_id=""))
        assert "hub_id" in str(excinfo.value)

    def test_rejects_utilization_above_100(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            HubStatus(**_valid_hub_status(current_utilization_pct=101.0))
        assert "current_utilization_pct" in str(excinfo.value)

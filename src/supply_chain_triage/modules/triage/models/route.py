"""Route and hub models for Impact Agent ripple analysis.

Internal models — NOT used as output_schema. These model the multi-leg
Indian logistics corridor network and hub capacity for cascade analysis.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RouteLeg(BaseModel):
    """A single leg in a multi-leg logistics route."""

    model_config = ConfigDict(extra="forbid")

    leg_number: int = Field(..., ge=1)
    origin_hub: str = Field(..., min_length=1)
    destination_hub: str = Field(..., min_length=1)
    distance_km: float = Field(..., gt=0)
    estimated_hours: float = Field(..., gt=0)


class RouteDefinition(BaseModel):
    """Complete route definition for an Indian logistics corridor."""

    model_config = ConfigDict(extra="forbid")

    route_id: str = Field(..., min_length=1)
    corridor_name: str
    legs: list[RouteLeg]
    total_distance_km: float = Field(..., gt=0)


class HubCapacityWindow(BaseModel):
    """Capacity snapshot for a specific time window at a hub."""

    model_config = ConfigDict(extra="forbid")

    window_label: Literal["next_24h", "24_to_48h", "48_to_72h"]
    utilization_pct: float = Field(..., ge=0, le=100)
    pending_shipments: int = Field(..., ge=0)


class HubStatus(BaseModel):
    """Current status and capacity of a logistics hub/facility."""

    model_config = ConfigDict(extra="forbid")

    hub_id: str = Field(..., min_length=1)
    hub_name: str
    city: str
    hub_type: Literal["major", "distribution", "transit", "regional"]
    capacity_containers_per_day: int = Field(..., gt=0)
    current_utilization_pct: float = Field(..., ge=0, le=100)
    congestion_level: Literal["LOW", "MODERATE", "HIGH", "CRITICAL"]
    time_windows: list[HubCapacityWindow] = Field(default_factory=list)

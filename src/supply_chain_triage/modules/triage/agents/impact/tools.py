"""Impact-agent tools -- Firestore lookups and financial-impact computation.

Per ``.claude/rules/tools.md``: async for I/O, return
``{"status": "success"|"error", ...}``, per-turn cache in state.
"""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext  # type: ignore[attr-defined]  # noqa: TC002

from supply_chain_triage.core.config import get_firestore_client
from supply_chain_triage.utils.logging import get_logger, log_firestore_op

logger = get_logger(__name__)

# Firestore collection names
_SHIPMENTS_COLLECTION = "shipments"
_CUSTOMERS_COLLECTION = "customers"
_ROUTES_COLLECTION = "routes"
_HUBS_COLLECTION = "hubs"

# Financial-impact heuristic constants
_REROUTING_COST_PER_KM_INR = 15
_HOLDING_COST_PER_DAY_PER_CONTAINER_INR = 500
_OPPORTUNITY_COST_LTV_FACTOR = 0.10


async def get_affected_shipments(
    scope_type: str,
    scope_value: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Retrieve shipments affected by an exception, filtered by scope.

    Args:
        scope_type: Query dimension -- one of "vehicle_id", "route_id",
            or "region".
        scope_value: The value to filter on (e.g. "MH-04-XX-1234").
        tool_context: ADK tool context (provides state + actions).

    Returns:
        ``{"status": "success", "data": {"shipments": [...], "count": N}}``
        on hit, ``{"status": "error", "error_message": str}`` on failure.
    """
    allowed_scopes = {"vehicle_id", "route_id", "region"}
    if scope_type not in allowed_scopes:
        return {
            "status": "error",
            "error_message": (
                f"Invalid scope_type {scope_type!r}; must be one of {sorted(allowed_scopes)}"
            ),
        }

    cache_key = f"cache:shipments:{scope_type}:{scope_value}"
    if cached := tool_context.state.get(cache_key):
        return {"status": "success", "data": cached}

    try:
        db = get_firestore_client()
        query = (
            db.collection(_SHIPMENTS_COLLECTION)
            .where(filter=("status", "==", "in_transit"))
            .where(filter=(scope_type, "==", scope_value))
        )
        docs = [doc async for doc in query.stream()]

        shipments = []
        for doc in docs:
            raw = doc.to_dict() or {}
            shipments.append(
                {
                    "shipment_id": doc.id,
                    "customer_id": raw.get("customer_id"),
                    "value_inr": raw.get("value_inr"),
                    "destination": raw.get("destination"),
                    "deadline": raw.get("deadline"),
                    "vehicle_id": raw.get("vehicle_id"),
                    "route_id": raw.get("route_id"),
                }
            )

        log_firestore_op(
            op="query",
            collection=_SHIPMENTS_COLLECTION,
            doc_count=len(shipments),
            duration_ms=0,
        )

        data = {"shipments": shipments, "count": len(shipments)}
        tool_context.state[cache_key] = data
        return {"status": "success", "data": data}

    except Exception as exc:
        logger.error(
            "tool_failed",
            tool_name="get_affected_shipments",
            error_class=type(exc).__name__,
        )
        return {
            "status": "error",
            "error_message": (f"Failed to query shipments: {type(exc).__name__}"),
        }


async def get_shipment_details(
    shipment_id: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Retrieve full details for a single shipment.

    Args:
        shipment_id: Firestore document ID for the shipment.
        tool_context: ADK tool context (provides state + actions).

    Returns:
        ``{"status": "success", "data": {...}}`` on hit,
        ``{"status": "error", "error_message": str}`` on miss or failure.
    """
    cache_key = f"cache:shipment:{shipment_id}"
    if cached := tool_context.state.get(cache_key):
        return {"status": "success", "data": cached}

    try:
        db = get_firestore_client()
        doc = await db.collection(_SHIPMENTS_COLLECTION).document(shipment_id).get()

        if not doc.exists:
            return {
                "status": "error",
                "error_message": f"Shipment {shipment_id!r} not found",
            }

        raw = doc.to_dict() or {}
        raw["shipment_id"] = doc.id

        log_firestore_op(
            op="get",
            collection=_SHIPMENTS_COLLECTION,
            doc_count=1,
            duration_ms=0,
        )

        tool_context.state[cache_key] = raw
        return {"status": "success", "data": raw}

    except Exception as exc:
        logger.error(
            "tool_failed",
            tool_name="get_shipment_details",
            error_class=type(exc).__name__,
        )
        return {
            "status": "error",
            "error_message": (f"Failed to fetch shipment: {type(exc).__name__}"),
        }


async def get_customer_profile(
    customer_id: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Retrieve customer CRM profile for impact assessment.

    Args:
        customer_id: Firestore document ID for the customer.
        tool_context: ADK tool context (provides state + actions).

    Returns:
        ``{"status": "success", "data": {...}}`` on hit,
        ``{"status": "error", "error_message": str}`` on miss or failure.
    """
    cache_key = f"cache:customer:{customer_id}"
    if cached := tool_context.state.get(cache_key):
        return {"status": "success", "data": cached}

    try:
        db = get_firestore_client()
        doc = await db.collection(_CUSTOMERS_COLLECTION).document(customer_id).get()

        if not doc.exists:
            return {
                "status": "error",
                "error_message": f"Customer {customer_id!r} not found",
            }

        raw = doc.to_dict() or {}
        raw["customer_id"] = doc.id

        log_firestore_op(
            op="get",
            collection=_CUSTOMERS_COLLECTION,
            doc_count=1,
            duration_ms=0,
        )

        tool_context.state[cache_key] = raw
        return {"status": "success", "data": raw}

    except Exception as exc:
        logger.error(
            "tool_failed",
            tool_name="get_customer_profile",
            error_class=type(exc).__name__,
        )
        return {
            "status": "error",
            "error_message": (f"Failed to fetch customer: {type(exc).__name__}"),
        }


async def get_route_and_hub_status(
    route_id: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Retrieve route definition and current hub capacity for cascade analysis.

    Args:
        route_id: Firestore document ID for the route.
        tool_context: ADK tool context (provides state + actions).

    Returns:
        ``{"status": "success", "data": {"route": {...}, "hubs": [...]}}``
        on hit, ``{"status": "error", "error_message": str}`` on miss
        or failure.
    """
    cache_key = f"cache:route:{route_id}"
    if cached := tool_context.state.get(cache_key):
        return {"status": "success", "data": cached}

    try:
        db = get_firestore_client()
        route_doc = await db.collection(_ROUTES_COLLECTION).document(route_id).get()

        if not route_doc.exists:
            return {
                "status": "error",
                "error_message": f"Route {route_id!r} not found",
            }

        route_raw = route_doc.to_dict() or {}
        route_raw["route_id"] = route_doc.id

        # Collect unique hub IDs from route legs
        hub_ids: set[str] = set()
        for leg in route_raw.get("legs", []):
            if origin := leg.get("origin_hub"):
                hub_ids.add(origin)
            if destination := leg.get("destination_hub"):
                hub_ids.add(destination)

        # Fetch hub documents
        hubs: list[dict[str, Any]] = []
        for hub_id in sorted(hub_ids):
            hub_doc = await db.collection(_HUBS_COLLECTION).document(hub_id).get()
            if hub_doc.exists:
                hub_data = hub_doc.to_dict() or {}
                hub_data["hub_id"] = hub_doc.id
                hubs.append(hub_data)

        log_firestore_op(
            op="get",
            collection=_ROUTES_COLLECTION,
            doc_count=1,
            duration_ms=0,
        )
        log_firestore_op(
            op="get",
            collection=_HUBS_COLLECTION,
            doc_count=len(hubs),
            duration_ms=0,
        )

        data: dict[str, Any] = {"route": route_raw, "hubs": hubs}
        tool_context.state[cache_key] = data
        return {"status": "success", "data": data}

    except Exception as exc:
        logger.error(
            "tool_failed",
            tool_name="get_route_and_hub_status",
            error_class=type(exc).__name__,
        )
        return {
            "status": "error",
            "error_message": (f"Failed to fetch route/hubs: {type(exc).__name__}"),
        }


def calculate_financial_impact(  # noqa: PLR0913 - ADK exposes each param individually
    shipment_value_inr: int,
    penalty_per_hour_inr: int,
    max_penalty_inr: int,
    estimated_delay_hours: float,
    rerouting_distance_km: float,
    holding_days: float,
    container_count: int,
    customer_ltv_inr: int,
    churn_risk_score: float,
    tool_context: ToolContext,  # noqa: ARG001 - required by ADK tool signature convention
) -> dict[str, Any]:
    """Calculate deterministic financial impact for a shipment.

    Pure computation -- no I/O. Called by the Impact agent to quantify the
    total financial exposure from a delay or disruption.

    Args:
        shipment_value_inr: Declared value of the shipment in rupees.
        penalty_per_hour_inr: SLA penalty per hour of delay.
        max_penalty_inr: Maximum penalty cap from SLA terms.
        estimated_delay_hours: Estimated delay in hours.
        rerouting_distance_km: Additional distance if rerouted (0 if none).
        holding_days: Estimated warehouse holding days.
        container_count: Number of containers/units.
        customer_ltv_inr: Customer lifetime value in rupees.
        churn_risk_score: Customer churn probability (0.0-1.0).
        tool_context: ADK tool context (provides state + actions).

    Returns:
        ``{"status": "success", "data": {"penalty_exposure_inr": ..., ...}}``
        with a full breakdown of each cost component and explanatory notes.
    """
    penalty = min(
        int(penalty_per_hour_inr * estimated_delay_hours),
        max_penalty_inr,
    )
    rerouting_cost = int(rerouting_distance_km * _REROUTING_COST_PER_KM_INR)
    holding_cost = int(
        holding_days * _HOLDING_COST_PER_DAY_PER_CONTAINER_INR * container_count,
    )
    opportunity_cost = int(
        customer_ltv_inr * churn_risk_score * _OPPORTUNITY_COST_LTV_FACTOR,
    )
    total = shipment_value_inr + penalty + rerouting_cost + holding_cost + opportunity_cost

    notes_parts = [
        f"Shipment value: INR {shipment_value_inr:,}",
        (
            f"SLA penalty: INR {penalty_per_hour_inr:,}/hr x "
            f"{estimated_delay_hours:.1f}h = INR {int(penalty_per_hour_inr * estimated_delay_hours):,}, "
            f"capped at INR {max_penalty_inr:,} -> INR {penalty:,}"
        ),
        (
            f"Rerouting cost: {rerouting_distance_km:.0f} km x "
            f"INR {_REROUTING_COST_PER_KM_INR}/km = INR {rerouting_cost:,}"
        ),
        (
            f"Holding cost: {holding_days:.1f} days x "
            f"{container_count} containers x "
            f"INR {_HOLDING_COST_PER_DAY_PER_CONTAINER_INR}/day = "
            f"INR {holding_cost:,}"
        ),
        (
            f"Opportunity cost: INR {customer_ltv_inr:,} LTV x "
            f"{churn_risk_score:.0%} churn x "
            f"{_OPPORTUNITY_COST_LTV_FACTOR:.0%} factor = "
            f"INR {opportunity_cost:,}"
        ),
        f"Total financial exposure: INR {total:,}",
    ]

    return {
        "status": "success",
        "data": {
            "penalty_exposure_inr": penalty,
            "rerouting_cost_inr": rerouting_cost,
            "holding_cost_inr": holding_cost,
            "opportunity_cost_inr": opportunity_cost,
            "shipment_value_inr": shipment_value_inr,
            "total_impact_inr": total,
            "breakdown_notes": "; ".join(notes_parts),
        },
    }

"""POST /driver/route-plan — mounted directly on `evagg.edge_app`, same
reasoning as `reservation_router.py`: `RoutePlanService`'s dependencies
(`VehicleStore`, `LocationRepository`, `RoutingClient`) are all
edge_app-local, so `vehicle_id` ownership can be checked straight off the
driver's verified JWT (`require_driver_id`) with no forwarder/extra hop.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from evagg.driver_app.route_planner import RoutePlan, RoutePlanService
from evagg.driver_app.routing_client import RoutingError
from evagg.driver_app.vehicles import VehicleNotFoundError
from evagg.identity.driver_session import require_driver_id


class LatLng(BaseModel):
    lat: float
    lng: float


class RoutePlanRequest(BaseModel):
    vehicle_id: uuid.UUID
    origin: LatLng
    destination: LatLng


def _plan_to_dict(plan: RoutePlan) -> dict:
    return {
        "distance_km": plan.distance_km,
        "duration_minutes": plan.duration_minutes,
        "charging_stop_needed": plan.charging_stop_needed,
        "suggested_charger": (
            {
                "id": plan.suggested_charger.id,
                "name": plan.suggested_charger.name,
                "lat": plan.suggested_charger.lat,
                "lng": plan.suggested_charger.lng,
            }
            if plan.suggested_charger
            else None
        ),
    }


def build_route_planner_router(service_dependency) -> APIRouter:
    router = APIRouter(prefix="/driver/route-plan", tags=["driver-route-planner"])

    @router.post("")
    async def plan_route(
        body: RoutePlanRequest,
        driver_id: uuid.UUID = Depends(require_driver_id),
        service: RoutePlanService = Depends(service_dependency),
    ) -> dict:
        try:
            plan = await service.plan_route(
                driver_id,
                body.vehicle_id,
                (body.origin.lat, body.origin.lng),
                (body.destination.lat, body.destination.lng),
            )
        except VehicleNotFoundError as exc:
            raise HTTPException(status_code=404, detail="vehicle not found") from exc
        except RoutingError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return _plan_to_dict(plan)

    return router

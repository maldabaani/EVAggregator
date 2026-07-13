"""Route planner: distance/duration from a `RoutingClient` plus a
same-trip charging-stop recommendation, using the driver's vehicle
profile (Task/Phase 0's "My Cars"). Two figures here are documented
assumptions rather than real telemetry, since neither exists anywhere in
this system: `ASSUMED_STARTING_SOC_FRACTION` (no live state-of-charge
reading from the vehicle) and `ASSUMED_CONSUMPTION_KWH_PER_KM` (no
per-vehicle efficiency data). Both are conservative, roughly
mid-size-EV-average defaults — enough to decide "does this trip need a
charging stop at all", not a precise remaining-range prediction.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from evagg.driver_app.geo import haversine_km
from evagg.driver_app.routing_client import RoutingClient
from evagg.driver_app.vehicles import VehicleNotFoundError, VehicleStore
from evagg.ocpi.locations import LocationRepository

ASSUMED_STARTING_SOC_FRACTION = 0.8
ASSUMED_CONSUMPTION_KWH_PER_KM = 0.18


@dataclass(frozen=True)
class SuggestedCharger:
    id: str
    name: str | None
    lat: float
    lng: float


@dataclass(frozen=True)
class RoutePlan:
    distance_km: float
    duration_minutes: float
    charging_stop_needed: bool
    suggested_charger: SuggestedCharger | None


class RoutePlanService:
    def __init__(
        self,
        routing_client: RoutingClient,
        vehicle_store: VehicleStore,
        location_repository: LocationRepository,
    ) -> None:
        self._routing_client = routing_client
        self._vehicle_store = vehicle_store
        self._location_repository = location_repository

    async def plan_route(
        self,
        driver_id: uuid.UUID,
        vehicle_id: uuid.UUID,
        origin: tuple[float, float],
        destination: tuple[float, float],
    ) -> RoutePlan:
        vehicle = await self._vehicle_store.get(vehicle_id)
        if vehicle is None or vehicle.driver_id != driver_id:
            raise VehicleNotFoundError(str(vehicle_id))

        estimate = await self._routing_client.get_route(origin, destination)
        usable_range_km = (
            vehicle.battery_capacity_kwh * ASSUMED_STARTING_SOC_FRACTION / ASSUMED_CONSUMPTION_KWH_PER_KM
        )
        needs_stop = estimate.distance_km > usable_range_km

        suggested_charger = None
        if needs_stop:
            suggested_charger = await self._nearest_published_charger(destination)

        return RoutePlan(
            distance_km=estimate.distance_km,
            duration_minutes=estimate.duration_minutes,
            charging_stop_needed=needs_stop,
            suggested_charger=suggested_charger,
        )

    async def _nearest_published_charger(self, point: tuple[float, float]) -> SuggestedCharger | None:
        locations = await self._location_repository.list_all()
        candidates = [loc for loc in locations if loc.publish]
        if not candidates:
            return None
        nearest = min(
            candidates,
            key=lambda loc: haversine_km(point, (float(loc.coordinates.latitude), float(loc.coordinates.longitude))),
        )
        return SuggestedCharger(
            id=nearest.id,
            name=nearest.name,
            lat=float(nearest.coordinates.latitude),
            lng=float(nearest.coordinates.longitude),
        )

"""GET /map/chargers — driver-facing charger map, filtered to a bounding
box. Built on the same OCPI-synced `LocationRepository` as the roaming
Locations module (Task 1.2), since it's the same published-location data;
this is just a driver-shaped read of it, not a second copy.

`min_kw`/`max_price`/`connector_type` are accepted for forward
compatibility with the mobile app's filter UI but not yet enforced —
`OCPILocation`'s read model doesn't carry per-connector power/price data,
only a single location-level `evse_status`. Enforcing those filters needs
extending Task 1.2's location sync to carry per-EVSE detail.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from evagg.ocpi.locations import LocationRepository


def _parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    min_lat, min_lng, max_lat, max_lng = (float(v) for v in bbox.split(","))
    return min_lat, min_lng, max_lat, max_lng


def build_map_router(location_repository_dependency) -> APIRouter:
    router = APIRouter(prefix="/map", tags=["driver-map"])

    @router.get("/chargers")
    async def list_chargers(
        bbox: str,
        available_only: bool = False,
        min_kw: float | None = None,
        max_price: float | None = None,
        connector_type: str | None = None,
        repo: LocationRepository = Depends(location_repository_dependency),
    ) -> dict:
        min_lat, min_lng, max_lat, max_lng = _parse_bbox(bbox)
        locations = await repo.list_all()
        pins = []
        for loc in locations:
            if not loc.publish:
                continue
            lat = float(loc.coordinates.latitude)
            lng = float(loc.coordinates.longitude)
            if not (min_lat <= lat <= max_lat and min_lng <= lng <= max_lng):
                continue
            if available_only and loc.evse_status != "AVAILABLE":
                continue
            pins.append({"id": loc.id, "name": loc.name, "lat": lat, "lng": lng, "status": loc.evse_status})
        return {"data": pins}

    return router

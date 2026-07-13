import uuid
from datetime import datetime, timezone

import pytest

from evagg.driver_app.route_planner import RoutePlanService
from evagg.driver_app.routing_client import FakeRoutingClient
from evagg.driver_app.vehicles import InMemoryVehicleStore, VehicleNotFoundError
from evagg.ocpi.domain import OCPIGeoLocation, OCPILocation
from evagg.ocpi.locations import InMemoryLocationRepository

DUBAI = (25.2048, 55.2708)
ABU_DHABI = (24.4539, 54.3773)
DRIVER_ID = uuid.uuid4()


def _location(loc_id: str, lat: str, lng: str, publish: bool = True) -> OCPILocation:
    return OCPILocation(
        id=loc_id,
        party_id="ABC",
        country_code="AE",
        publish=publish,
        name=f"Station {loc_id}",
        address="1 Main St",
        city="Dubai",
        country="ARE",
        coordinates=OCPIGeoLocation(latitude=lat, longitude=lng),
        last_updated=datetime.now(timezone.utc),
        evse_status="AVAILABLE",
    )


async def _build_service(locations: list[OCPILocation] | None = None) -> tuple[RoutePlanService, InMemoryVehicleStore]:
    vehicle_store = InMemoryVehicleStore()
    location_repository = InMemoryLocationRepository(locations or [])
    service = RoutePlanService(FakeRoutingClient(), vehicle_store, location_repository)
    return service, vehicle_store


@pytest.mark.asyncio
async def test_a_short_trip_within_range_needs_no_charging_stop():
    service, vehicle_store = await _build_service()
    vehicle = await vehicle_store.create(DRIVER_ID, "Tesla", "Model 3", "CCS2", battery_capacity_kwh=75.0)

    plan = await service.plan_route(DRIVER_ID, vehicle.id, DUBAI, ABU_DHABI)

    assert plan.charging_stop_needed is False
    assert plan.suggested_charger is None
    assert plan.distance_km > 0


@pytest.mark.asyncio
async def test_a_long_trip_beyond_range_suggests_the_nearest_published_charger():
    near_destination = _location("CP-near", "24.40", "54.30")
    far_away = _location("CP-far", "40.0", "10.0")
    service, vehicle_store = await _build_service([far_away, near_destination])
    # Small battery -> low usable range, so even the Dubai-Abu Dhabi trip exceeds it.
    vehicle = await vehicle_store.create(DRIVER_ID, "Nano", "EV", "Type2", battery_capacity_kwh=5.0)

    plan = await service.plan_route(DRIVER_ID, vehicle.id, DUBAI, ABU_DHABI)

    assert plan.charging_stop_needed is True
    assert plan.suggested_charger is not None
    assert plan.suggested_charger.id == "CP-near"


@pytest.mark.asyncio
async def test_unpublished_chargers_are_never_suggested():
    only_unpublished = _location("CP-hidden", "24.40", "54.30", publish=False)
    service, vehicle_store = await _build_service([only_unpublished])
    vehicle = await vehicle_store.create(DRIVER_ID, "Nano", "EV", "Type2", battery_capacity_kwh=5.0)

    plan = await service.plan_route(DRIVER_ID, vehicle.id, DUBAI, ABU_DHABI)

    assert plan.charging_stop_needed is True
    assert plan.suggested_charger is None


@pytest.mark.asyncio
async def test_an_unknown_vehicle_raises():
    service, _ = await _build_service()

    with pytest.raises(VehicleNotFoundError):
        await service.plan_route(DRIVER_ID, uuid.uuid4(), DUBAI, ABU_DHABI)


@pytest.mark.asyncio
async def test_another_drivers_vehicle_raises_not_found_too():
    service, vehicle_store = await _build_service()
    other_driver = uuid.uuid4()
    vehicle = await vehicle_store.create(other_driver, "Tesla", "Model 3", "CCS2", battery_capacity_kwh=75.0)

    with pytest.raises(VehicleNotFoundError):
        await service.plan_route(DRIVER_ID, vehicle.id, DUBAI, ABU_DHABI)

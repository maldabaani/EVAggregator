import uuid

import pytest

from evagg.driver_app.vehicles import InMemoryVehicleStore, VehicleNotFoundError


@pytest.mark.asyncio
async def test_created_vehicle_defaults_to_plug_and_charge_disabled():
    store = InMemoryVehicleStore()
    driver_id = uuid.uuid4()

    vehicle = await store.create(driver_id, "Tesla", "Model 3", "CCS2", 75.0)

    assert vehicle.driver_id == driver_id
    assert vehicle.plug_and_charge_enabled is False


@pytest.mark.asyncio
async def test_list_for_driver_only_returns_that_drivers_vehicles():
    store = InMemoryVehicleStore()
    driver_a = uuid.uuid4()
    driver_b = uuid.uuid4()
    await store.create(driver_a, "Tesla", "Model 3", "CCS2", 75.0)
    await store.create(driver_b, "Nissan", "Leaf", "CHAdeMO", 40.0)

    vehicles = await store.list_for_driver(driver_a)

    assert len(vehicles) == 1
    assert vehicles[0].make == "Tesla"


@pytest.mark.asyncio
async def test_set_plug_and_charge_toggles_the_flag():
    store = InMemoryVehicleStore()
    vehicle = await store.create(uuid.uuid4(), "Tesla", "Model 3", "CCS2", 75.0)

    updated = await store.set_plug_and_charge(vehicle.id, True)

    assert updated.plug_and_charge_enabled is True
    assert (await store.get(vehicle.id)).plug_and_charge_enabled is True


@pytest.mark.asyncio
async def test_set_plug_and_charge_on_unknown_vehicle_raises():
    store = InMemoryVehicleStore()

    with pytest.raises(VehicleNotFoundError):
        await store.set_plug_and_charge(uuid.uuid4(), True)


@pytest.mark.asyncio
async def test_delete_removes_the_vehicle():
    store = InMemoryVehicleStore()
    vehicle = await store.create(uuid.uuid4(), "Tesla", "Model 3", "CCS2", 75.0)

    await store.delete(vehicle.id)

    assert await store.get(vehicle.id) is None

"""Driver vehicle profiles ("My Cars") — foundation for the route planner
(needs battery capacity/range) and per-vehicle Plug & Charge opt-in.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from typing import Protocol


@dataclass(frozen=True)
class Vehicle:
    id: uuid.UUID
    driver_id: uuid.UUID
    make: str
    model: str
    connector_type: str
    battery_capacity_kwh: float
    plug_and_charge_enabled: bool = False


class VehicleNotFoundError(Exception):
    pass


class VehicleStore(Protocol):
    async def create(
        self, driver_id: uuid.UUID, make: str, model: str, connector_type: str, battery_capacity_kwh: float
    ) -> Vehicle: ...

    async def list_for_driver(self, driver_id: uuid.UUID) -> list[Vehicle]: ...

    async def get(self, vehicle_id: uuid.UUID) -> Vehicle | None: ...

    async def set_plug_and_charge(self, vehicle_id: uuid.UUID, enabled: bool) -> Vehicle: ...

    async def delete(self, vehicle_id: uuid.UUID) -> None: ...


class InMemoryVehicleStore:
    def __init__(self) -> None:
        self._vehicles: dict[uuid.UUID, Vehicle] = {}

    async def create(
        self, driver_id: uuid.UUID, make: str, model: str, connector_type: str, battery_capacity_kwh: float
    ) -> Vehicle:
        vehicle = Vehicle(
            id=uuid.uuid4(),
            driver_id=driver_id,
            make=make,
            model=model,
            connector_type=connector_type,
            battery_capacity_kwh=battery_capacity_kwh,
        )
        self._vehicles[vehicle.id] = vehicle
        return vehicle

    async def list_for_driver(self, driver_id: uuid.UUID) -> list[Vehicle]:
        return [v for v in self._vehicles.values() if v.driver_id == driver_id]

    async def get(self, vehicle_id: uuid.UUID) -> Vehicle | None:
        return self._vehicles.get(vehicle_id)

    async def set_plug_and_charge(self, vehicle_id: uuid.UUID, enabled: bool) -> Vehicle:
        existing = self._vehicles.get(vehicle_id)
        if existing is None:
            raise VehicleNotFoundError(str(vehicle_id))
        updated = replace(existing, plug_and_charge_enabled=enabled)
        self._vehicles[vehicle_id] = updated
        return updated

    async def delete(self, vehicle_id: uuid.UUID) -> None:
        self._vehicles.pop(vehicle_id, None)

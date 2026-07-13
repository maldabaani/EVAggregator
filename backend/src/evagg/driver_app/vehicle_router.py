"""POST/GET /driver/vehicles, PATCH .../plug-and-charge, DELETE — the "My
Cars" feature. `driver_id` always comes from the verified access token
(`require_driver_id`), never from the request body, so a driver can only
ever see or modify their own vehicles.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from evagg.driver_app.vehicles import Vehicle, VehicleNotFoundError, VehicleStore
from evagg.identity.driver_session import require_driver_id


class CreateVehicleRequest(BaseModel):
    make: str
    model: str
    connector_type: str
    battery_capacity_kwh: float


class SetPlugAndChargeRequest(BaseModel):
    enabled: bool


def _vehicle_to_dict(vehicle: Vehicle) -> dict:
    return {
        "id": str(vehicle.id),
        "make": vehicle.make,
        "model": vehicle.model,
        "connector_type": vehicle.connector_type,
        "battery_capacity_kwh": vehicle.battery_capacity_kwh,
        "plug_and_charge_enabled": vehicle.plug_and_charge_enabled,
    }


def build_vehicle_router(store_dependency) -> APIRouter:
    router = APIRouter(prefix="/driver/vehicles", tags=["driver-vehicles"])

    async def _owned_vehicle_or_404(vehicle_id: uuid.UUID, driver_id: uuid.UUID, store: VehicleStore) -> Vehicle:
        vehicle = await store.get(vehicle_id)
        if vehicle is None or vehicle.driver_id != driver_id:
            raise HTTPException(status_code=404, detail="vehicle not found")
        return vehicle

    @router.get("")
    async def list_vehicles(
        driver_id: uuid.UUID = Depends(require_driver_id),
        store: VehicleStore = Depends(store_dependency),
    ) -> dict:
        vehicles = await store.list_for_driver(driver_id)
        return {"data": [_vehicle_to_dict(v) for v in vehicles]}

    @router.post("")
    async def create_vehicle(
        body: CreateVehicleRequest,
        driver_id: uuid.UUID = Depends(require_driver_id),
        store: VehicleStore = Depends(store_dependency),
    ) -> dict:
        vehicle = await store.create(driver_id, body.make, body.model, body.connector_type, body.battery_capacity_kwh)
        return _vehicle_to_dict(vehicle)

    @router.patch("/{vehicle_id}/plug-and-charge")
    async def set_plug_and_charge(
        vehicle_id: uuid.UUID,
        body: SetPlugAndChargeRequest,
        driver_id: uuid.UUID = Depends(require_driver_id),
        store: VehicleStore = Depends(store_dependency),
    ) -> dict:
        await _owned_vehicle_or_404(vehicle_id, driver_id, store)
        try:
            updated = await store.set_plug_and_charge(vehicle_id, body.enabled)
        except VehicleNotFoundError:
            raise HTTPException(status_code=404, detail="vehicle not found")
        return _vehicle_to_dict(updated)

    @router.delete("/{vehicle_id}")
    async def delete_vehicle(
        vehicle_id: uuid.UUID,
        driver_id: uuid.UUID = Depends(require_driver_id),
        store: VehicleStore = Depends(store_dependency),
    ) -> Response:
        await _owned_vehicle_or_404(vehicle_id, driver_id, store)
        await store.delete(vehicle_id)
        return Response(status_code=204)

    return router

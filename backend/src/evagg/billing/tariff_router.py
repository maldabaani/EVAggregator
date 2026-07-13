"""Task 3.1 — POST /admin/tariffs, PUT /admin/tariffs/{id}, GET
/admin/tariffs/{id}/preview."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from evagg.billing.tariff_calculator import TariffComponentInput
from evagg.billing.tariff_validation import TariffValidationError
from evagg.billing.tariffs import TariffNotFoundError, TariffService


class TariffComponentBody(BaseModel):
    type: str
    price_minor_units: int
    step_size: int = 1
    applies_after_minutes: int | None = None


class CreateTariffBody(BaseModel):
    tenant_id: uuid.UUID
    name: str
    components: list[TariffComponentBody]


class UpdateTariffBody(BaseModel):
    name: str
    components: list[TariffComponentBody]


def _to_inputs(components: list[TariffComponentBody]) -> list[TariffComponentInput]:
    return [
        TariffComponentInput(
            type=c.type, price_minor_units=c.price_minor_units, step_size=c.step_size,
            applies_after_minutes=c.applies_after_minutes,
        )
        for c in components
    ]


def build_tariff_router(service_dependency) -> APIRouter:
    router = APIRouter(prefix="/admin/tariffs", tags=["tariffs"])

    @router.get("")
    async def list_tariffs(
        tenant_id: uuid.UUID | None = None, service: TariffService = Depends(service_dependency)
    ) -> dict:
        tariffs = await service.list_all_tariffs()
        if tenant_id is not None:
            tariffs = [t for t in tariffs if t.tenant_id == tenant_id]
        return {"data": [{"id": str(t.id), "name": t.name, "currency": t.currency} for t in tariffs]}

    @router.post("")
    async def create_tariff(body: CreateTariffBody, service: TariffService = Depends(service_dependency)) -> dict:
        try:
            tariff = await service.create_tariff(body.tenant_id, body.name, _to_inputs(body.components))
        except TariffValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        return {"id": str(tariff.id), "name": tariff.name, "currency": tariff.currency}

    @router.put("/{tariff_id}")
    async def update_tariff(
        tariff_id: uuid.UUID, body: UpdateTariffBody, service: TariffService = Depends(service_dependency)
    ) -> dict:
        try:
            tariff = await service.update_tariff(tariff_id, body.name, _to_inputs(body.components))
        except TariffValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        except TariffNotFoundError:
            raise HTTPException(status_code=404, detail="tariff not found")
        return {"id": str(tariff.id), "name": tariff.name, "currency": tariff.currency}

    @router.get("/{tariff_id}/preview")
    async def preview_tariff(
        tariff_id: uuid.UUID,
        duration_min: float,
        kwh: float,
        idle_min: float = 0.0,
        service: TariffService = Depends(service_dependency),
    ) -> dict:
        try:
            total = await service.preview(tariff_id, duration_min, kwh, idle_min)
        except TariffNotFoundError:
            raise HTTPException(status_code=404, detail="tariff not found")
        return {"total_minor_units": total}

    return router

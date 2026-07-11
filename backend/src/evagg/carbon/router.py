"""Task 1.4 — `GET /internal/carbon-intensity?zone=` used by Epic 5's
Insights forecast and, later, smart charging scheduling.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from evagg.carbon.service import CarbonIntensityService, ZoneNotSupportedError


def build_carbon_router(service_dependency) -> APIRouter:
    router = APIRouter(prefix="/internal", tags=["carbon"])

    @router.get("/carbon-intensity")
    async def get_carbon_intensity(
        zone: str, service: CarbonIntensityService = Depends(service_dependency)
    ) -> dict:
        try:
            country_code, area_code = zone.split(":", 1)
        except ValueError:
            raise HTTPException(status_code=400, detail="zone must be formatted as {country_code}:{area_code}")

        try:
            result = await service.get_intensity(country_code, area_code)
        except ZoneNotSupportedError:
            raise HTTPException(status_code=404, detail=f"zone not supported: {zone}")

        return {"zone": zone, "value": result.value, "unit": "gCO2/kWh", "stale": result.stale}

    return router

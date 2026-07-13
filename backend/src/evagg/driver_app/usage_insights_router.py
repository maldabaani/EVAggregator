"""GET /driver/usage-insights — mounted directly on `evagg.edge_app`,
same reasoning as `route_planner_router.py`: `UsageInsightsService`'s
dependencies (`SessionHistoryStore`, `LocationRepository`) are both
edge_app-local, so the driver's own id comes straight off their verified
JWT (`require_driver_id`) with no forwarder/extra hop.
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends

from evagg.driver_app.usage_insights import DailyUsagePoint, UsageInsightsService
from evagg.identity.driver_session import require_driver_id


def _point_to_dict(point: DailyUsagePoint) -> dict:
    return {
        "usage_date": point.usage_date.isoformat(),
        "session_count": point.session_count,
        "kwh_total": point.kwh_total,
        "cost_total_minor_units": point.cost_total_minor_units,
        "top_site_name": point.top_site_name,
    }


def build_usage_insights_router(service_dependency) -> APIRouter:
    router = APIRouter(prefix="/driver/usage-insights", tags=["driver-usage-insights"])

    @router.get("")
    async def get_daily_usage(
        date_from: date,
        date_to: date,
        driver_id: uuid.UUID = Depends(require_driver_id),
        service: UsageInsightsService = Depends(service_dependency),
    ) -> dict:
        points = await service.get_daily_usage(driver_id, date_from, date_to)
        return {"data": [_point_to_dict(p) for p in points]}

    return router

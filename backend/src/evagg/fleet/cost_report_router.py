"""Task 4.4 — GET /admin/teams/{team_id}/cost-report[.csv]. The backend
service (`CostReportService`) existed since Task 4.4 originally shipped, but
no endpoint ever exposed it — this is the portal's first entry point onto it.
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response

from evagg.fleet.cost_report import GROUP_BY_DRIVER, GROUP_BY_SITE, CostReportService, export_cost_report_csv

_VALID_GROUP_BY = {GROUP_BY_DRIVER, GROUP_BY_SITE}


def _validate_group_by(group_by: str) -> None:
    if group_by not in _VALID_GROUP_BY:
        raise HTTPException(status_code=422, detail=f"group_by must be one of {sorted(_VALID_GROUP_BY)}")


def _report_dict(report) -> dict:
    return {
        "group_by": report.group_by,
        "rows": [
            {
                "key": row.key,
                "session_count": row.session_count,
                "kwh_total": row.kwh_total,
                "cost_total_minor_units": row.cost_total_minor_units,
            }
            for row in report.rows
        ],
        "total_session_count": report.total_session_count,
        "total_kwh": report.total_kwh,
        "total_cost_minor_units": report.total_cost_minor_units,
        "incomplete_dates": [d.isoformat() for d in report.incomplete_dates],
    }


def build_cost_report_router(service_dependency) -> APIRouter:
    router = APIRouter(prefix="/admin/teams/{team_id}/cost-report", tags=["cost-report"])

    @router.get("")
    async def get_cost_report(
        team_id: uuid.UUID,
        date_from: date,
        date_to: date,
        group_by: str = GROUP_BY_DRIVER,
        service: CostReportService = Depends(service_dependency),
    ) -> dict:
        _validate_group_by(group_by)
        report = await service.generate_report(team_id, date_from, date_to, group_by)
        return _report_dict(report)

    @router.get("/csv")
    async def get_cost_report_csv(
        team_id: uuid.UUID,
        date_from: date,
        date_to: date,
        group_by: str = GROUP_BY_DRIVER,
        service: CostReportService = Depends(service_dependency),
    ) -> Response:
        _validate_group_by(group_by)
        report = await service.generate_report(team_id, date_from, date_to, group_by)
        csv_text = export_cost_report_csv(report)
        return Response(
            content=csv_text,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="cost-report-{team_id}.csv"'},
        )

    return router

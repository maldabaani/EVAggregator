"""Task 4.4 — B2B corporate cost allocation dashboard: reads exclusively from
the pre-aggregated rollup table (Task 4.4's own nightly job populates it),
never scanning raw session records as fleet size grows.
"""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass
from datetime import date

from evagg.fleet.rollup import RollupStore

GROUP_BY_DRIVER = "driver"
GROUP_BY_SITE = "site"

_NO_SITE_KEY = uuid.UUID(int=0)


@dataclass(frozen=True)
class CostReportRow:
    key: str
    session_count: int
    kwh_total: int
    cost_total_minor_units: int


@dataclass(frozen=True)
class CostReport:
    group_by: str
    rows: list[CostReportRow]
    total_session_count: int
    total_kwh: int
    total_cost_minor_units: int
    incomplete_dates: list[date]


class CostReportService:
    """Depends only on `RollupStore` — there is no raw-session dependency to
    even accidentally read from, by construction."""

    def __init__(self, rollup_store: RollupStore) -> None:
        self._rollup_store = rollup_store

    async def generate_report(
        self, team_id: uuid.UUID, date_from: date, date_to: date, group_by: str = GROUP_BY_DRIVER
    ) -> CostReport:
        rollups = await self._rollup_store.query(team_id, date_from, date_to)
        incomplete_dates = await self._rollup_store.incomplete_dates_in_range(date_from, date_to)

        grouped: dict[uuid.UUID, dict] = {}
        for rollup in rollups:
            key = rollup.driver_id if group_by == GROUP_BY_DRIVER else (rollup.site_id or _NO_SITE_KEY)
            bucket = grouped.setdefault(key, {"session_count": 0, "kwh_total": 0, "cost_total_minor_units": 0})
            bucket["session_count"] += rollup.session_count
            bucket["kwh_total"] += rollup.kwh_total
            bucket["cost_total_minor_units"] += rollup.cost_total_minor_units

        rows = [
            CostReportRow(
                key=str(key), session_count=v["session_count"], kwh_total=v["kwh_total"],
                cost_total_minor_units=v["cost_total_minor_units"],
            )
            for key, v in grouped.items()
        ]
        return CostReport(
            group_by=group_by,
            rows=rows,
            total_session_count=sum(r.session_count for r in rows),
            total_kwh=sum(r.kwh_total for r in rows),
            total_cost_minor_units=sum(r.cost_total_minor_units for r in rows),
            incomplete_dates=incomplete_dates,
        )


def export_cost_report_csv(report: CostReport) -> str:
    """Reuses the export pattern from Epic 1 Task 1.3's reconciliation CSV
    for consistency: header row, one row per group, values matching exactly
    what the filtered dashboard view shows."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([report.group_by, "session_count", "kwh_total", "cost_total_minor_units"])
    for row in report.rows:
        writer.writerow([row.key, row.session_count, row.kwh_total, row.cost_total_minor_units])
    return buffer.getvalue()

"""Driver-facing usage insights (Task 5.4's own note: "mirrors the shape
of the backend's per-driver rollup" — `DriverDailyUsage`, `Task 4.4's
team_driver_daily_usage` table). That table is written by nothing (no
per-driver nightly rollup job exists, only the team-scoped one in
`evagg.fleet.rollup`), so rather than add a second unused table, this
computes the same daily-grouped shape live from `SessionHistoryStore` —
real completed-session records, just not pre-aggregated overnight.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from evagg.driver_app.session_history import CompletedSession, SessionHistoryStore
from evagg.ocpi.locations import LocationRepository


@dataclass(frozen=True)
class DailyUsagePoint:
    usage_date: date
    session_count: int
    kwh_total: float
    cost_total_minor_units: int
    top_site_name: str | None


class UsageInsightsService:
    def __init__(self, session_history_store: SessionHistoryStore, location_repository: LocationRepository) -> None:
        self._session_history_store = session_history_store
        self._location_repository = location_repository

    async def get_daily_usage(self, driver_id: uuid.UUID, date_from: date, date_to: date) -> list[DailyUsagePoint]:
        sessions = await self._session_history_store.list_for_driver(driver_id, date_from, date_to)

        by_day: dict[date, list[CompletedSession]] = defaultdict(list)
        for session in sessions:
            by_day[session.ended_at.date()].append(session)

        points = []
        for usage_date, day_sessions in sorted(by_day.items()):
            top_site_name = await self._top_site_name(day_sessions)
            points.append(
                DailyUsagePoint(
                    usage_date=usage_date,
                    session_count=len(day_sessions),
                    kwh_total=sum(s.energy_kwh for s in day_sessions),
                    cost_total_minor_units=sum(s.cost_minor_units for s in day_sessions),
                    top_site_name=top_site_name,
                )
            )
        return points

    async def _top_site_name(self, day_sessions: list[CompletedSession]) -> str | None:
        # "Top" = most energy delivered that day at a single charger, the
        # most meaningful ranking available without a richer per-site
        # session count.
        by_charger: dict[str, float] = defaultdict(float)
        for session in day_sessions:
            by_charger[session.charger_id] += session.energy_kwh
        if not by_charger:
            return None
        top_charger_id = max(by_charger, key=lambda charger_id: by_charger[charger_id])
        location = await self._location_repository.get(top_charger_id)
        return location.name if location is not None else top_charger_id

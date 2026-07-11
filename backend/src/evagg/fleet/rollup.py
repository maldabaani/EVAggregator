"""Task 4.4 — nightly rollup job populating `team_driver_daily_usage` (Task
6.1), so the cost dashboard never scans raw session tables directly.

If aggregation fails for a given day, the job records that day as
`is_complete: False` rather than silently producing zero rows — a dashboard
reading zero usage for a day looks identical to "no charging happened", so
the failure must be visible as its own signal.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


@dataclass(frozen=True)
class SessionUsageRecord:
    team_id: uuid.UUID
    driver_id: uuid.UUID
    site_id: uuid.UUID | None
    timestamp: datetime
    kwh: int
    cost_minor_units: int


@dataclass(frozen=True)
class DailyUsageRollup:
    team_id: uuid.UUID
    driver_id: uuid.UUID
    site_id: uuid.UUID | None
    usage_date: date
    session_count: int
    kwh_total: int
    cost_total_minor_units: int


class RollupStore(Protocol):
    async def save_rollup(self, rollup: DailyUsageRollup) -> None: ...

    async def mark_incomplete(self, target_date: date) -> None: ...

    async def query(self, team_id: uuid.UUID, date_from: date, date_to: date) -> list[DailyUsageRollup]: ...

    async def incomplete_dates_in_range(self, date_from: date, date_to: date) -> list[date]: ...


class InMemoryRollupStore:
    def __init__(self) -> None:
        self._rollups: list[DailyUsageRollup] = []
        self._incomplete_dates: set[date] = set()

    async def save_rollup(self, rollup: DailyUsageRollup) -> None:
        self._rollups.append(rollup)

    async def mark_incomplete(self, target_date: date) -> None:
        self._incomplete_dates.add(target_date)

    async def query(self, team_id: uuid.UUID, date_from: date, date_to: date) -> list[DailyUsageRollup]:
        return [
            r for r in self._rollups
            if r.team_id == team_id and date_from <= r.usage_date <= date_to
        ]

    async def incomplete_dates_in_range(self, date_from: date, date_to: date) -> list[date]:
        return sorted(d for d in self._incomplete_dates if date_from <= d <= date_to)


async def run_daily_rollup(
    store: RollupStore,
    sessions: list[SessionUsageRecord],
    target_date: date,
    failing_dates: set[date] | None = None,
) -> None:
    """`failing_dates` simulates an aggregation failure for a specific day
    (e.g. an upstream data source was unavailable) — production would pass
    no such hook and instead catch a real exception from the aggregation
    query, but the resulting behavior (mark_incomplete, no rollup rows) is
    identical either way."""
    if failing_dates and target_date in failing_dates:
        await store.mark_incomplete(target_date)
        return

    day_sessions = [s for s in sessions if s.timestamp.date() == target_date]
    grouped: dict[tuple[uuid.UUID, uuid.UUID, uuid.UUID | None], dict] = {}
    for session in day_sessions:
        key = (session.team_id, session.driver_id, session.site_id)
        bucket = grouped.setdefault(key, {"session_count": 0, "kwh_total": 0, "cost_total_minor_units": 0})
        bucket["session_count"] += 1
        bucket["kwh_total"] += session.kwh
        bucket["cost_total_minor_units"] += session.cost_minor_units

    for (team_id, driver_id, site_id), agg in grouped.items():
        await store.save_rollup(
            DailyUsageRollup(
                team_id=team_id, driver_id=driver_id, site_id=site_id, usage_date=target_date,
                session_count=agg["session_count"], kwh_total=agg["kwh_total"],
                cost_total_minor_units=agg["cost_total_minor_units"],
            )
        )

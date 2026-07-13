"""Completed-session record, written once per successful stop
(`SessionStartService.stop_session`) — the piece `usage_insights.py`
needs that nothing in this system previously kept: no persistent log of
finished charging sessions existed anywhere, only the in-flight
`ActiveTransaction`/`SessionChargerBinding` state that a stop already
clears.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


@dataclass(frozen=True)
class CompletedSession:
    session_id: str
    driver_id: uuid.UUID
    charger_id: str
    started_at: datetime
    ended_at: datetime
    energy_kwh: float
    cost_minor_units: int
    currency: str


class SessionHistoryStore(Protocol):
    async def record(self, session: CompletedSession) -> None: ...

    async def list_for_driver(
        self, driver_id: uuid.UUID, date_from: date, date_to: date
    ) -> list[CompletedSession]: ...


class InMemorySessionHistoryStore:
    def __init__(self) -> None:
        self._sessions: list[CompletedSession] = []

    async def record(self, session: CompletedSession) -> None:
        self._sessions.append(session)

    async def list_for_driver(
        self, driver_id: uuid.UUID, date_from: date, date_to: date
    ) -> list[CompletedSession]:
        return [
            s
            for s in self._sessions
            if s.driver_id == driver_id and date_from <= s.ended_at.date() <= date_to
        ]

"""Connector status tracking, updated by StatusNotification (Task 2.2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class ConnectorStatus:
    charger_id: str
    connector_id: int
    status: str
    error_code: str | None


class ConnectorStore(Protocol):
    async def update_status(
        self, charger_id: str, connector_id: int, status: str, error_code: str | None
    ) -> None: ...

    async def get_status(self, charger_id: str, connector_id: int) -> ConnectorStatus | None: ...


class InMemoryConnectorStore:
    def __init__(self) -> None:
        self._statuses: dict[tuple[str, int], ConnectorStatus] = {}

    async def update_status(self, charger_id: str, connector_id: int, status: str, error_code: str | None) -> None:
        self._statuses[(charger_id, connector_id)] = ConnectorStatus(charger_id, connector_id, status, error_code)

    async def get_status(self, charger_id: str, connector_id: int) -> ConnectorStatus | None:
        return self._statuses.get((charger_id, connector_id))

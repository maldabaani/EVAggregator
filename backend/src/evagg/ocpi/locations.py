"""In-memory location store used by the router/tests. Production reads from
the materialized read model synced from internal charger/site tables (Task
1.2) rather than this — this module exists so Task 1.1's version-negotiation
and shim-enforcement work is testable without that dependency yet existing.
"""

from __future__ import annotations

from typing import Protocol

from evagg.ocpi.domain import OCPILocation


class LocationRepository(Protocol):
    async def get(self, location_id: str) -> OCPILocation | None: ...

    async def list_all(self) -> list[OCPILocation]: ...


class InMemoryLocationRepository:
    def __init__(self, locations: list[OCPILocation] | None = None) -> None:
        self._locations: dict[str, OCPILocation] = {loc.id: loc for loc in (locations or [])}

    def add(self, location: OCPILocation) -> None:
        self._locations[location.id] = location

    async def get(self, location_id: str) -> OCPILocation | None:
        return self._locations.get(location_id)

    async def list_all(self) -> list[OCPILocation]:
        return list(self._locations.values())

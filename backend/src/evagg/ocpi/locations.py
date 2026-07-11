"""Location read model, synced from internal charger/site tables (Task 1.2's
`LocationSyncService`) rather than queried live from OCPP state on every
roaming call. Task 1.1 uses the same store, seeded directly, before that sync
mechanism existed.
"""

from __future__ import annotations

from typing import Protocol

from evagg.ocpi.domain import OCPILocation


class LocationRepository(Protocol):
    async def get(self, location_id: str) -> OCPILocation | None: ...

    async def list_all(self) -> list[OCPILocation]: ...

    async def upsert(self, location: OCPILocation) -> None: ...


class InMemoryLocationRepository:
    def __init__(self, locations: list[OCPILocation] | None = None) -> None:
        self._locations: dict[str, OCPILocation] = {loc.id: loc for loc in (locations or [])}

    def add(self, location: OCPILocation) -> None:
        self._locations[location.id] = location

    async def get(self, location_id: str) -> OCPILocation | None:
        return self._locations.get(location_id)

    async def list_all(self) -> list[OCPILocation]:
        return list(self._locations.values())

    async def upsert(self, location: OCPILocation) -> None:
        self._locations[location.id] = location

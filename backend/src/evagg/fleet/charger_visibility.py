"""Task 4.3 — team-scoped charger visibility for the map query.

Enforcement happens here, at the query layer: a `team_only` charger the
requesting driver isn't authorized for is never included in the response at
all, rather than being fetched and hidden client-side (which would leak it
to anyone inspecting network traffic).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from evagg.fleet.team_membership import MembershipStore

PUBLIC = "public"
TEAM_ONLY = "team_only"


@dataclass(frozen=True)
class BoundingBox:
    min_lat: float
    min_lng: float
    max_lat: float
    max_lng: float

    def contains(self, lat: float, lng: float) -> bool:
        return self.min_lat <= lat <= self.max_lat and self.min_lng <= lng <= self.max_lng


@dataclass(frozen=True)
class ChargerSummary:
    id: uuid.UUID
    visibility: str  # 'public' | 'team_only'
    latitude: float
    longitude: float


class ChargerAccessRepository(Protocol):
    async def list_chargers(self) -> list[ChargerSummary]: ...

    async def get_authorized_team_ids_for_charger(self, charger_id: uuid.UUID) -> set[uuid.UUID]: ...


class InMemoryChargerAccessRepository:
    def __init__(self) -> None:
        self._chargers: dict[uuid.UUID, ChargerSummary] = {}
        self._team_access: dict[uuid.UUID, set[uuid.UUID]] = {}

    def add_charger(self, charger: ChargerSummary) -> None:
        self._chargers[charger.id] = charger

    def grant_team_access(self, charger_id: uuid.UUID, team_id: uuid.UUID) -> None:
        self._team_access.setdefault(charger_id, set()).add(team_id)

    async def list_chargers(self) -> list[ChargerSummary]:
        return list(self._chargers.values())

    async def get_authorized_team_ids_for_charger(self, charger_id: uuid.UUID) -> set[uuid.UUID]:
        return self._team_access.get(charger_id, set())


class MapChargerQueryService:
    def __init__(self, charger_repo: ChargerAccessRepository, membership_store: MembershipStore) -> None:
        self._charger_repo = charger_repo
        self._membership_store = membership_store

    async def query_visible_chargers(
        self, driver_id: uuid.UUID, bbox: BoundingBox | None = None
    ) -> list[ChargerSummary]:
        driver_team_ids = await self._membership_store.list_team_ids_for_driver(driver_id)
        all_chargers = await self._charger_repo.list_chargers()

        visible: list[ChargerSummary] = []
        for charger in all_chargers:
            if bbox is not None and not bbox.contains(charger.latitude, charger.longitude):
                continue

            if charger.visibility == PUBLIC:
                visible.append(charger)
                continue

            authorized_teams = await self._charger_repo.get_authorized_team_ids_for_charger(charger.id)
            if authorized_teams & driver_team_ids:
                visible.append(charger)

        return visible

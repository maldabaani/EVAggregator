"""Task 4.2 — team membership: `admin` manages the team and sees all team
billing; `member` uses team chargers with billing visibility limited to
themselves.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

ADMIN = "admin"
MEMBER = "member"


@dataclass(frozen=True)
class DriverTeamMembership:
    driver_id: uuid.UUID
    team_id: uuid.UUID
    role: str


class MembershipStore(Protocol):
    async def create(self, driver_id: uuid.UUID, team_id: uuid.UUID, role: str) -> DriverTeamMembership: ...

    async def list_for_team(self, team_id: uuid.UUID) -> list[DriverTeamMembership]: ...

    async def list_team_ids_for_driver(self, driver_id: uuid.UUID) -> set[uuid.UUID]: ...


class InMemoryMembershipStore:
    def __init__(self) -> None:
        self._memberships: list[DriverTeamMembership] = []

    async def create(self, driver_id: uuid.UUID, team_id: uuid.UUID, role: str) -> DriverTeamMembership:
        membership = DriverTeamMembership(driver_id=driver_id, team_id=team_id, role=role)
        self._memberships.append(membership)
        return membership

    async def list_for_team(self, team_id: uuid.UUID) -> list[DriverTeamMembership]:
        return [m for m in self._memberships if m.team_id == team_id]

    async def list_team_ids_for_driver(self, driver_id: uuid.UUID) -> set[uuid.UUID]:
        return {m.team_id for m in self._memberships if m.driver_id == driver_id}

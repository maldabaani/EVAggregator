"""Authorize handling (Task 2.2): local id_tag whitelist first, falling back
to an OCPI roaming token check for tags unknown locally (Epic 1 Task 1.2,
not built yet — `RoamingTokenChecker` is the seam that integration will plug
into; until then, an unknown tag with no roaming checker configured is
treated as Invalid rather than silently accepted).
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol


class AuthStatus(str, Enum):
    ACCEPTED = "Accepted"
    BLOCKED = "Blocked"
    EXPIRED = "Expired"
    INVALID = "Invalid"


class LocalIdTagStore(Protocol):
    async def lookup(self, id_tag: str) -> AuthStatus | None:
        """Returns None if the tag is not known locally at all — the caller
        should fall back to the roaming check, not treat this as Invalid."""
        ...


class RoamingTokenChecker(Protocol):
    async def check(self, id_tag: str) -> AuthStatus: ...


class InMemoryLocalIdTagStore:
    def __init__(self, statuses: dict[str, AuthStatus] | None = None) -> None:
        self._statuses = dict(statuses or {})

    def set_status(self, id_tag: str, status: AuthStatus) -> None:
        self._statuses[id_tag] = status

    async def lookup(self, id_tag: str) -> AuthStatus | None:
        return self._statuses.get(id_tag)


class InMemoryRoamingTokenChecker:
    def __init__(self, statuses: dict[str, AuthStatus] | None = None) -> None:
        self._statuses = dict(statuses or {})
        self.checked_tags: list[str] = []

    def set_status(self, id_tag: str, status: AuthStatus) -> None:
        self._statuses[id_tag] = status

    async def check(self, id_tag: str) -> AuthStatus:
        self.checked_tags.append(id_tag)
        return self._statuses.get(id_tag, AuthStatus.INVALID)


class Authorizer:
    def __init__(self, local_store: LocalIdTagStore, roaming_checker: RoamingTokenChecker) -> None:
        self._local_store = local_store
        self._roaming_checker = roaming_checker

    async def authorize(self, id_tag: str) -> AuthStatus:
        local_status = await self._local_store.lookup(id_tag)
        if local_status is not None:
            return local_status
        return await self._roaming_checker.check(id_tag)

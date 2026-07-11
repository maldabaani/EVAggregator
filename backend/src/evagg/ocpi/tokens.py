"""Task 1.2 — eMSP -> CPO token whitelisting: `PUT /tokens/{token_uid}`
whitelists a foreign driver token locally, cached in Redis
(`ocpi:token:{token_uid}` -> whitelisted/blacklisted), TTL refreshed on every
Authorize check so an actively-roaming driver's session is never interrupted
by an expiring cache entry.

`OcpiRoamingTokenChecker` implements Epic 2 Task 2.2's `RoamingTokenChecker`
protocol directly — this is the concrete fallback `Authorizer.authorize`
calls for tags unknown to the local whitelist, closing the loop the two
epics were designed around.
"""

from __future__ import annotations

import time
from typing import Callable, Protocol

from evagg.ocpp_gateway.authorize import AuthStatus

WHITELISTED = "whitelisted"
BLACKLISTED = "blacklisted"


def token_cache_key(token_uid: str) -> str:
    return f"ocpi:token:{token_uid}"


class TokenWhitelistCache(Protocol):
    async def set_status(self, token_uid: str, status: str, ttl_seconds: int) -> None: ...

    async def get_status(self, token_uid: str) -> str | None: ...

    async def refresh_ttl(self, token_uid: str, ttl_seconds: int) -> None: ...


class InMemoryTokenWhitelistCache:
    """Reference implementation. Tracks the same expiry semantics as Redis's
    TTL using an injectable clock, so tests can assert refresh behavior
    without sleeping for real time."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._entries: dict[str, tuple[str, float]] = {}  # token_uid -> (status, expires_at)

    async def set_status(self, token_uid: str, status: str, ttl_seconds: int) -> None:
        self._entries[token_uid] = (status, self._clock() + ttl_seconds)

    async def get_status(self, token_uid: str) -> str | None:
        entry = self._entries.get(token_uid)
        if entry is None:
            return None
        status, expires_at = entry
        if self._clock() >= expires_at:
            del self._entries[token_uid]
            return None
        return status

    async def refresh_ttl(self, token_uid: str, ttl_seconds: int) -> None:
        entry = self._entries.get(token_uid)
        if entry is None:
            return
        status, _ = entry
        self._entries[token_uid] = (status, self._clock() + ttl_seconds)

    def expires_at(self, token_uid: str) -> float | None:
        entry = self._entries.get(token_uid)
        return entry[1] if entry else None


class RedisTokenWhitelistCache:
    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    async def set_status(self, token_uid: str, status: str, ttl_seconds: int) -> None:
        await self._redis.set(token_cache_key(token_uid), status, ex=ttl_seconds)

    async def get_status(self, token_uid: str) -> str | None:
        value = await self._redis.get(token_cache_key(token_uid))
        return value.decode() if isinstance(value, bytes) else value

    async def refresh_ttl(self, token_uid: str, ttl_seconds: int) -> None:
        await self._redis.expire(token_cache_key(token_uid), ttl_seconds)


class TokenWhitelistService:
    """PUT /tokens/{token_uid} handler logic."""

    def __init__(self, cache: TokenWhitelistCache, default_ttl_seconds: int = 3600) -> None:
        self._cache = cache
        self._default_ttl_seconds = default_ttl_seconds

    async def whitelist_token(self, token_uid: str) -> None:
        await self._cache.set_status(token_uid, WHITELISTED, self._default_ttl_seconds)

    async def blacklist_token(self, token_uid: str) -> None:
        await self._cache.set_status(token_uid, BLACKLISTED, self._default_ttl_seconds)


class OcpiRoamingTokenChecker:
    def __init__(self, cache: TokenWhitelistCache, ttl_seconds: int = 3600) -> None:
        self._cache = cache
        self._ttl_seconds = ttl_seconds

    async def check(self, id_tag: str) -> AuthStatus:
        status = await self._cache.get_status(id_tag)
        if status is None:
            return AuthStatus.INVALID
        if status == BLACKLISTED:
            return AuthStatus.BLOCKED
        await self._cache.refresh_ttl(id_tag, self._ttl_seconds)
        return AuthStatus.ACCEPTED

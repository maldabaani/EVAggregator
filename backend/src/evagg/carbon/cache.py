"""Task 1.4 — carbon intensity cache: `carbon:{country_code}:{zone}` ->
`{value, fetched_at}`. Freshness (the 15-minute TTL) is decided by comparing
`fetched_at` against the caller's clock rather than relying on Redis's own
key expiry, because a stale-but-present value must still be servable as a
fallback — a hard TTL-based delete would destroy exactly the data the
fallback path needs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

# Long backstop TTL in Redis, purely for storage hygiene (unmapped zones that
# stop being queried eventually fall out of cache) — not the freshness signal.
CACHE_BACKSTOP_TTL_SECONDS = 7 * 24 * 60 * 60


@dataclass(frozen=True)
class CarbonCacheEntry:
    value: float
    fetched_at: datetime


def cache_key(country_code: str, area_code: str) -> str:
    return f"carbon:{country_code}:{area_code}"


class CarbonCache(Protocol):
    async def get(self, country_code: str, area_code: str) -> CarbonCacheEntry | None: ...

    async def set(self, country_code: str, area_code: str, value: float, fetched_at: datetime) -> None: ...


class InMemoryCarbonCache:
    def __init__(self) -> None:
        self._entries: dict[str, CarbonCacheEntry] = {}

    async def get(self, country_code: str, area_code: str) -> CarbonCacheEntry | None:
        return self._entries.get(cache_key(country_code, area_code))

    async def set(self, country_code: str, area_code: str, value: float, fetched_at: datetime) -> None:
        self._entries[cache_key(country_code, area_code)] = CarbonCacheEntry(value=value, fetched_at=fetched_at)


class RedisCarbonCache:
    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    async def get(self, country_code: str, area_code: str) -> CarbonCacheEntry | None:
        raw = await self._redis.get(cache_key(country_code, area_code))
        if raw is None:
            return None
        payload = json.loads(raw)
        return CarbonCacheEntry(value=payload["value"], fetched_at=datetime.fromisoformat(payload["fetched_at"]))

    async def set(self, country_code: str, area_code: str, value: float, fetched_at: datetime) -> None:
        payload = json.dumps({"value": value, "fetched_at": fetched_at.isoformat()})
        await self._redis.set(cache_key(country_code, area_code), payload, ex=CACHE_BACKSTOP_TTL_SECONDS)

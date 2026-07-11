"""Per-tenant / per-user token-bucket-style rate limiting at the gateway layer
(Task 6.3), so a single tenant's traffic spike can't overwhelm internal
services.
"""

from __future__ import annotations

import time
from typing import Protocol, runtime_checkable


@runtime_checkable
class RateLimiter(Protocol):
    async def allow(self, key: str, limit: int, window_seconds: int) -> bool: ...


class InMemoryRateLimiter:
    """Fixed-window limiter for tests and local dev. Production uses
    `RedisRateLimiter` so limits are shared across gateway replicas."""

    def __init__(self) -> None:
        self._windows: dict[str, tuple[int, float]] = {}

    async def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        count, window_start = self._windows.get(key, (0, now))
        if now - window_start >= window_seconds:
            count, window_start = 0, now
        count += 1
        self._windows[key] = (count, window_start)
        return count <= limit


class RedisRateLimiter:
    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    async def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        current = await self._redis.incr(key)
        if current == 1:
            await self._redis.expire(key, window_seconds)
        return current <= limit

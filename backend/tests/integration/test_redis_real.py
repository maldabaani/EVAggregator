"""Real-Redis integration coverage for the two production Redis-backed
classes whose unit tests (tests/unit/gateway/test_rate_limit.py,
tests/unit/carbon/test_redis_cache.py) exercise via fakeredis. fakeredis
reimplements the Redis command set in Python rather than talking to a real
server, so it can silently diverge from real Redis wire behavior (TTL
precision, atomicity under real round-trips). This runs the exact same
classes against an actual Redis instance — a local `redis-server` satisfies
this in the sandbox that wrote this suite, docker-compose's `redis:7-alpine`
satisfies it in CI.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import pytest
import redis.asyncio as redis_asyncio

from evagg.carbon.cache import RedisCarbonCache
from evagg.core.config import settings
from evagg.gateway.rate_limit import RedisRateLimiter
from conftest import requires_redis


@pytest.fixture
async def redis_client():
    client = redis_asyncio.from_url(settings.redis_url)
    yield client
    await client.aclose()


def _unique_key(prefix: str) -> str:
    return f"{prefix}:{uuid.uuid4()}"


@requires_redis
@pytest.mark.asyncio
async def test_rate_limiter_blocks_once_over_limit_against_real_redis(redis_client):
    limiter = RedisRateLimiter(redis_client)
    key = _unique_key("test:rate-limit")

    for _ in range(3):
        assert await limiter.allow(key, limit=3, window_seconds=60)

    assert not await limiter.allow(key, limit=3, window_seconds=60)


@requires_redis
@pytest.mark.asyncio
async def test_rate_limiter_window_actually_expires_against_real_redis(redis_client):
    limiter = RedisRateLimiter(redis_client)
    key = _unique_key("test:rate-limit-window")

    for _ in range(2):
        assert await limiter.allow(key, limit=2, window_seconds=1)
    assert not await limiter.allow(key, limit=2, window_seconds=1)

    await asyncio.sleep(1.2)  # real Redis key TTL, not a mocked clock

    assert await limiter.allow(key, limit=2, window_seconds=1)


@requires_redis
@pytest.mark.asyncio
async def test_rate_limiter_concurrent_requests_never_exceed_limit_against_real_redis(redis_client):
    """INCR is atomic in real Redis even under genuine concurrent round-trips
    (unlike a naive read-modify-write) — this is exactly the property
    fakeredis's in-process implementation can't meaningfully prove."""
    limiter = RedisRateLimiter(redis_client)
    key = _unique_key("test:rate-limit-concurrent")

    results = await asyncio.gather(*(limiter.allow(key, limit=5, window_seconds=60) for _ in range(10)))

    assert sum(results) == 5


@requires_redis
@pytest.mark.asyncio
async def test_carbon_cache_round_trips_through_real_redis(redis_client):
    cache = RedisCarbonCache(redis_client)
    country_code, area_code = "AE", _unique_key("zone")
    fetched_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    assert await cache.get(country_code, area_code) is None

    await cache.set(country_code, area_code, 312.5, fetched_at)
    entry = await cache.get(country_code, area_code)

    assert entry is not None
    assert entry.value == 312.5
    assert entry.fetched_at == fetched_at


@requires_redis
@pytest.mark.asyncio
async def test_carbon_cache_entry_carries_the_documented_backstop_ttl(redis_client):
    from evagg.carbon.cache import CACHE_BACKSTOP_TTL_SECONDS, cache_key

    cache = RedisCarbonCache(redis_client)
    country_code, area_code = "AE", _unique_key("zone-ttl")

    await cache.set(country_code, area_code, 100.0, datetime.now(timezone.utc))

    ttl = await redis_client.ttl(cache_key(country_code, area_code))

    assert 0 < ttl <= CACHE_BACKSTOP_TTL_SECONDS

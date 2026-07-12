from datetime import datetime, timezone

import fakeredis.aioredis
import pytest

from evagg.carbon.cache import RedisCarbonCache


@pytest.mark.asyncio
async def test_redis_cache_round_trips_value_and_fetched_at():
    redis_client = fakeredis.aioredis.FakeRedis()
    cache = RedisCarbonCache(redis_client)
    fetched_at = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    await cache.set("AE", "DXB", 250.0, fetched_at)
    entry = await cache.get("AE", "DXB")

    assert entry.value == 250.0
    assert entry.fetched_at == fetched_at


@pytest.mark.asyncio
async def test_redis_cache_returns_none_for_unknown_zone():
    redis_client = fakeredis.aioredis.FakeRedis()
    cache = RedisCarbonCache(redis_client)

    assert await cache.get("US", "CA") is None

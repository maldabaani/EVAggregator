import fakeredis.aioredis
import pytest

from evagg.ocpi.tokens import RedisTokenWhitelistCache, WHITELISTED


@pytest.mark.asyncio
async def test_redis_token_cache_round_trips_status_and_ttl():
    redis_client = fakeredis.aioredis.FakeRedis()
    cache = RedisTokenWhitelistCache(redis_client)

    await cache.set_status("TOKEN-1", WHITELISTED, ttl_seconds=120)
    assert await cache.get_status("TOKEN-1") == WHITELISTED

    await cache.refresh_ttl("TOKEN-1", ttl_seconds=600)
    ttl = await redis_client.ttl("ocpi:token:TOKEN-1")
    assert ttl > 120


@pytest.mark.asyncio
async def test_redis_token_cache_returns_none_for_unknown_token():
    redis_client = fakeredis.aioredis.FakeRedis()
    cache = RedisTokenWhitelistCache(redis_client)

    assert await cache.get_status("unknown") is None

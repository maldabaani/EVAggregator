import fakeredis.aioredis
import pytest

from evagg.gateway.rate_limit import InMemoryRateLimiter, RedisRateLimiter


@pytest.mark.asyncio
async def test_requests_under_limit_are_allowed():
    limiter = InMemoryRateLimiter()
    for _ in range(5):
        assert await limiter.allow("tenant:a", limit=5, window_seconds=60)


@pytest.mark.asyncio
async def test_request_exceeding_limit_is_blocked():
    limiter = InMemoryRateLimiter()
    for _ in range(5):
        await limiter.allow("tenant:a", limit=5, window_seconds=60)

    assert not await limiter.allow("tenant:a", limit=5, window_seconds=60)


@pytest.mark.asyncio
async def test_limits_are_isolated_per_key():
    limiter = InMemoryRateLimiter()
    for _ in range(5):
        await limiter.allow("tenant:a", limit=5, window_seconds=60)

    assert await limiter.allow("tenant:b", limit=5, window_seconds=60)


@pytest.mark.asyncio
async def test_redis_rate_limiter_blocks_once_over_limit():
    """Uses fakeredis (in-memory, no real network/socket) to exercise the
    production RedisRateLimiter's INCR/EXPIRE logic without a live Redis."""
    redis_client = fakeredis.aioredis.FakeRedis()
    limiter = RedisRateLimiter(redis_client)

    for _ in range(3):
        assert await limiter.allow("tenant:a", limit=3, window_seconds=60)

    assert not await limiter.allow("tenant:a", limit=3, window_seconds=60)

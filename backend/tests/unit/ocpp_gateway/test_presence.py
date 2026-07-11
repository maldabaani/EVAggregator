import uuid

import fakeredis.aioredis
import pytest

from evagg.ocpp_gateway.presence import InMemoryPresenceRegistry, RedisPresenceRegistry

TENANT_ID = uuid.uuid4()


async def _exercise_registry(registry) -> None:
    await registry.mark_online("CP-1", TENANT_ID, node_id="node-a", protocol_version="ocpp1.6", ttl_seconds=120)
    state = await registry.get("CP-1")
    assert state is not None
    assert state.status == "online"
    assert state.tenant_id == str(TENANT_ID)

    first_seen = state.last_seen
    await registry.refresh("CP-1", ttl_seconds=120)
    refreshed = await registry.get("CP-1")
    assert refreshed.last_seen >= first_seen

    await registry.mark_offline("CP-1")
    offline_state = await registry.get("CP-1")
    assert offline_state.status == "offline"

    assert await registry.get("unknown-charger") is None


@pytest.mark.asyncio
async def test_in_memory_presence_registry_lifecycle():
    await _exercise_registry(InMemoryPresenceRegistry())


@pytest.mark.asyncio
async def test_redis_presence_registry_lifecycle():
    """Uses fakeredis (in-memory, no real network/socket) to exercise the
    production Redis-backed registry's serialization round-trip."""
    redis_client = fakeredis.aioredis.FakeRedis()
    await _exercise_registry(RedisPresenceRegistry(redis_client))

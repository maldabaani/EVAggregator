import uuid

import pytest

from evagg.ocpp_gateway.presence import InMemoryPresenceRegistry
from evagg.ocpp_gateway.presence_api import get_bulk_presence, get_presence

TENANT_ID = uuid.uuid4()


@pytest.mark.asyncio
async def test_presence_bulk_read_returns_correct_states_for_multiple_chargers():
    registry = InMemoryPresenceRegistry()
    await registry.mark_online("CP-1", TENANT_ID, node_id="node-a", protocol_version="ocpp1.6", ttl_seconds=600)
    await registry.mark_online("CP-2", TENANT_ID, node_id="node-b", protocol_version="ocpp2.0.1", ttl_seconds=600)
    # CP-3 deliberately has no presence entry (never connected / offline).

    states = await get_bulk_presence(["CP-1", "CP-2", "CP-3"], registry)

    assert states["CP-1"].node_id == "node-a"
    assert states["CP-1"].protocol_version == "ocpp1.6"
    assert states["CP-2"].node_id == "node-b"
    assert states["CP-2"].protocol_version == "ocpp2.0.1"
    assert states["CP-3"] is None


@pytest.mark.asyncio
async def test_single_presence_read_returns_none_for_unknown_charger():
    registry = InMemoryPresenceRegistry()

    state = await get_presence("unknown-charger", registry)

    assert state is None


@pytest.mark.asyncio
async def test_single_presence_read_reflects_offline_status():
    registry = InMemoryPresenceRegistry()
    await registry.mark_online("CP-1", TENANT_ID, node_id="node-a", protocol_version="ocpp1.6", ttl_seconds=600)
    await registry.mark_offline("CP-1")

    state = await get_presence("CP-1", registry)

    assert state.status == "offline"

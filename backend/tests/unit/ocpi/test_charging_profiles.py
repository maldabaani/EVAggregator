from __future__ import annotations

import uuid

import pytest

from evagg.ocpi.charging_profiles import (
    ChargingProfilePeriod,
    ChargingProfileResultStatus,
    ChargingProfileService,
    InMemoryActiveChargingProfileStore,
    InMemorySessionChargerMap,
    SessionChargerBinding,
)
from evagg.ocpp_gateway.commands import (
    CommandOutcome,
    CommandStatus,
    FakeCommandTransport,
    InMemoryCommandLogStore,
    InMemoryConnectorCapacityProvider,
    InMemoryFirmwareUpdateStore,
    RemoteCommandService,
)
from evagg.ocpp_gateway.presence import InMemoryPresenceRegistry

TENANT_ID = uuid.uuid4()
CHARGER_ID = "CP-001"
SESSION_ID = "SESSION-1"


def _build_service():
    presence = InMemoryPresenceRegistry()
    transport = FakeCommandTransport()
    command_service = RemoteCommandService(
        presence, InMemoryCommandLogStore(), transport, InMemoryFirmwareUpdateStore()
    )
    session_map = InMemorySessionChargerMap()
    capacity_provider = InMemoryConnectorCapacityProvider()
    profile_store = InMemoryActiveChargingProfileStore()
    service = ChargingProfileService(session_map, profile_store, command_service, capacity_provider)
    return service, presence, transport, session_map, capacity_provider, profile_store


async def _mark_online(presence):
    await presence.mark_online(CHARGER_ID, TENANT_ID, node_id="node-a", protocol_version="ocpp1.6", ttl_seconds=600)


@pytest.mark.asyncio
async def test_unknown_session_returns_unknown_session_result():
    service, *_ = _build_service()

    result = await service.set_charging_profile(SESSION_ID, "W", [ChargingProfilePeriod(0, 7000)])

    assert result.result == ChargingProfileResultStatus.UNKNOWN_SESSION


@pytest.mark.asyncio
async def test_amp_based_profile_is_rejected():
    service, presence, _, session_map, _, _ = _build_service()
    await _mark_online(presence)
    session_map.set_binding(SESSION_ID, SessionChargerBinding(CHARGER_ID, TENANT_ID, connector_id=1))

    result = await service.set_charging_profile(SESSION_ID, "A", [ChargingProfilePeriod(0, 32)])

    assert result.result == ChargingProfileResultStatus.REJECTED
    assert "charging_rate_unit" in result.reason


@pytest.mark.asyncio
async def test_accepted_profile_is_dispatched_and_stored_as_active():
    service, presence, transport, session_map, _, profile_store = _build_service()
    await _mark_online(presence)
    session_map.set_binding(SESSION_ID, SessionChargerBinding(CHARGER_ID, TENANT_ID, connector_id=1))
    transport.set_outcome(CHARGER_ID, CommandOutcome(CommandStatus.ACCEPTED, {}))

    result = await service.set_charging_profile(
        SESSION_ID, "W", [ChargingProfilePeriod(0, 7000), ChargingProfilePeriod(1800, 3500)], duration=3600
    )

    assert result.result == ChargingProfileResultStatus.ACCEPTED
    assert len(transport.calls) == 1
    node_id, charger_id, _, command_type, payload, _ = transport.calls[0]
    assert node_id == "node-a"
    assert charger_id == CHARGER_ID
    assert command_type == "SetChargingProfile"
    assert payload["connectorId"] == 1
    assert payload["csChargingProfile"]["chargingSchedule"]["chargingRateUnit"] == "W"

    status, profile = await service.get_active_profile(SESSION_ID)
    assert status == ChargingProfileResultStatus.ACCEPTED
    assert profile is not None
    assert profile.duration == 3600
    assert len(profile.periods) == 2


@pytest.mark.asyncio
async def test_over_capacity_profile_is_rejected_and_not_stored():
    service, presence, _, session_map, capacity_provider, profile_store = _build_service()
    await _mark_online(presence)
    session_map.set_binding(SESSION_ID, SessionChargerBinding(CHARGER_ID, TENANT_ID, connector_id=1))
    capacity_provider.set_capacity(CHARGER_ID, 1, max_power_watts=5000)

    result = await service.set_charging_profile(SESSION_ID, "W", [ChargingProfilePeriod(0, 7000)])

    assert result.result == ChargingProfileResultStatus.REJECTED
    assert await profile_store.get(SESSION_ID) is None


@pytest.mark.asyncio
async def test_offline_charger_profile_is_rejected():
    service, presence, _, session_map, _, _ = _build_service()
    session_map.set_binding(SESSION_ID, SessionChargerBinding(CHARGER_ID, TENANT_ID, connector_id=1))

    result = await service.set_charging_profile(SESSION_ID, "W", [ChargingProfilePeriod(0, 7000)])

    assert result.result == ChargingProfileResultStatus.REJECTED


@pytest.mark.asyncio
async def test_charge_point_rejection_does_not_store_a_profile():
    service, presence, transport, session_map, _, profile_store = _build_service()
    await _mark_online(presence)
    session_map.set_binding(SESSION_ID, SessionChargerBinding(CHARGER_ID, TENANT_ID, connector_id=1))
    transport.set_outcome(CHARGER_ID, CommandOutcome(CommandStatus.REJECTED, {"reason": "unsupported"}))

    result = await service.set_charging_profile(SESSION_ID, "W", [ChargingProfilePeriod(0, 7000)])

    assert result.result == ChargingProfileResultStatus.REJECTED
    assert await profile_store.get(SESSION_ID) is None


@pytest.mark.asyncio
async def test_get_active_profile_for_a_known_session_with_no_profile_yet():
    service, presence, _, session_map, _, _ = _build_service()
    await _mark_online(presence)
    session_map.set_binding(SESSION_ID, SessionChargerBinding(CHARGER_ID, TENANT_ID, connector_id=1))

    status, profile = await service.get_active_profile(SESSION_ID)

    assert status == ChargingProfileResultStatus.ACCEPTED
    assert profile is None

"""Task 2.3 unit tests — all isolated (in-memory presence/command-log/
transport/firmware-store fakes, no real NATS or 30s waits)."""

from __future__ import annotations

import uuid

import pytest

from evagg.ocpp_gateway.commands import (
    ChargerOfflineError,
    ChargingProfileExceedsCapacityError,
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


def _build_service():
    presence = InMemoryPresenceRegistry()
    command_log = InMemoryCommandLogStore()
    transport = FakeCommandTransport()
    firmware_store = InMemoryFirmwareUpdateStore()
    service = RemoteCommandService(presence, command_log, transport, firmware_store)
    return service, presence, command_log, transport, firmware_store


async def _mark_online(presence, node_id: str = "node-a") -> None:
    await presence.mark_online(CHARGER_ID, TENANT_ID, node_id=node_id, protocol_version="ocpp1.6", ttl_seconds=600)


@pytest.mark.asyncio
async def test_remote_start_creates_command_log_and_awaits_response():
    service, presence, command_log, transport, _ = _build_service()
    await _mark_online(presence)
    transport.set_outcome(CHARGER_ID, CommandOutcome(CommandStatus.ACCEPTED, {"status": "Accepted"}))

    result = await service.send_command(CHARGER_ID, TENANT_ID, "RemoteStartTransaction", {"idTag": "TAG-1"})

    assert result.status == CommandStatus.ACCEPTED
    record = await command_log.get(result.command_id)
    assert record is not None
    assert record.status == CommandStatus.ACCEPTED
    assert record.responded_at is not None
    assert record.type == "RemoteStartTransaction"


@pytest.mark.asyncio
async def test_command_timeout_after_30s_marks_timed_out():
    service, presence, command_log, transport, _ = _build_service()
    await _mark_online(presence)
    transport.set_outcome(CHARGER_ID, CommandOutcome(CommandStatus.TIMED_OUT, None))

    result = await service.send_command(CHARGER_ID, TENANT_ID, "RemoteStartTransaction", {"idTag": "TAG-1"})

    assert result.status == CommandStatus.TIMED_OUT
    record = await command_log.get(result.command_id)
    assert record.status == CommandStatus.TIMED_OUT
    # Verify the transport was actually asked for the 30s default window.
    assert transport.calls[0][5] == 30.0


@pytest.mark.asyncio
async def test_offline_charger_command_fails_fast():
    service, presence, command_log, transport, _ = _build_service()
    # No handshake/mark_online -> charger has no presence entry at all.

    with pytest.raises(ChargerOfflineError):
        await service.send_command(CHARGER_ID, TENANT_ID, "RemoteStartTransaction", {"idTag": "TAG-1"})

    assert transport.calls == []  # never attempted delivery


@pytest.mark.asyncio
async def test_offline_charger_after_being_marked_offline_fails_fast():
    service, presence, command_log, transport, _ = _build_service()
    await _mark_online(presence)
    await presence.mark_offline(CHARGER_ID)

    with pytest.raises(ChargerOfflineError):
        await service.send_command(CHARGER_ID, TENANT_ID, "Reset", {"type": "Soft"})

    assert transport.calls == []


@pytest.mark.asyncio
async def test_firmware_status_notification_updates_tracking_record():
    service, presence, command_log, transport, firmware_store = _build_service()
    await _mark_online(presence)
    transport.set_outcome(CHARGER_ID, CommandOutcome(CommandStatus.ACCEPTED, {}))

    await service.start_firmware_update(CHARGER_ID, TENANT_ID, "2.1.0", "https://example.com/fw/2.1.0.bin")
    record = await firmware_store.get(CHARGER_ID, "2.1.0")
    assert record.status == "pending"

    await service.handle_firmware_status_notification(CHARGER_ID, "2.1.0", "downloading")
    assert (await firmware_store.get(CHARGER_ID, "2.1.0")).status == "downloading"

    await service.handle_firmware_status_notification(CHARGER_ID, "2.1.0", "installing")
    await service.handle_firmware_status_notification(CHARGER_ID, "2.1.0", "installed")
    assert (await firmware_store.get(CHARGER_ID, "2.1.0")).status == "installed"


@pytest.mark.asyncio
async def test_set_charging_profile_rejects_over_capacity_request():
    service, presence, command_log, transport, _ = _build_service()
    await _mark_online(presence)
    capacity_provider = InMemoryConnectorCapacityProvider()
    capacity_provider.set_capacity(CHARGER_ID, 1, max_power_watts=7_000)

    with pytest.raises(ChargingProfileExceedsCapacityError):
        await service.send_set_charging_profile(
            CHARGER_ID, TENANT_ID, connector_id=1, requested_watts=11_000,
            capacity_provider=capacity_provider, profile_payload={},
        )

    assert transport.calls == []  # rejected before ever reaching the charger


@pytest.mark.asyncio
async def test_set_charging_profile_within_capacity_is_sent():
    service, presence, command_log, transport, _ = _build_service()
    await _mark_online(presence)
    transport.set_outcome(CHARGER_ID, CommandOutcome(CommandStatus.ACCEPTED, {}))
    capacity_provider = InMemoryConnectorCapacityProvider()
    capacity_provider.set_capacity(CHARGER_ID, 1, max_power_watts=11_000)

    result = await service.send_set_charging_profile(
        CHARGER_ID, TENANT_ID, connector_id=1, requested_watts=7_000,
        capacity_provider=capacity_provider, profile_payload={"chargingProfileId": 1},
    )

    assert result.status == CommandStatus.ACCEPTED
    assert len(transport.calls) == 1


@pytest.mark.asyncio
async def test_command_routed_to_correct_gateway_node_via_presence_lookup():
    service, presence, command_log, transport, _ = _build_service()
    await _mark_online(presence, node_id="node-xyz")

    await service.send_command(CHARGER_ID, TENANT_ID, "UnlockConnector", {"connectorId": 1})

    assert transport.calls[0][0] == "node-xyz"
    assert transport.calls[0][1] == CHARGER_ID

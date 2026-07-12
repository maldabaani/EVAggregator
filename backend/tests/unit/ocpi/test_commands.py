from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from evagg.ocpi.charging_profiles import InMemorySessionChargerMap, SessionChargerBinding
from evagg.ocpi.commands import OcpiCommandResultStatus, OcpiCommandService
from evagg.ocpp_gateway.commands import (
    CommandOutcome,
    CommandStatus,
    FakeCommandTransport,
    InMemoryCommandLogStore,
    InMemoryFirmwareUpdateStore,
    RemoteCommandService,
)
from evagg.ocpp_gateway.presence import InMemoryPresenceRegistry
from evagg.ocpp_gateway.transactions import InMemoryTransactionRepository

TENANT_ID = uuid.uuid4()
CHARGER_ID = "CP-001"


def _build_service():
    presence = InMemoryPresenceRegistry()
    transport = FakeCommandTransport()
    command_service = RemoteCommandService(
        presence, InMemoryCommandLogStore(), transport, InMemoryFirmwareUpdateStore()
    )
    session_map = InMemorySessionChargerMap()
    transaction_repo = InMemoryTransactionRepository()
    service = OcpiCommandService(session_map, transaction_repo, command_service)
    return service, presence, transport, session_map, transaction_repo


async def _mark_online(presence, charger_id=CHARGER_ID):
    await presence.mark_online(charger_id, TENANT_ID, node_id="node-a", protocol_version="ocpp1.6", ttl_seconds=600)


@pytest.mark.asyncio
async def test_start_session_dispatches_remote_start_and_mints_a_session_binding():
    service, presence, transport, session_map, _ = _build_service()
    await _mark_online(presence)
    transport.set_outcome(CHARGER_ID, CommandOutcome(CommandStatus.ACCEPTED, {"status": "Accepted"}))

    result = await service.start_session(CHARGER_ID, TENANT_ID, "TAG-1", connector_id=1)

    assert result.result == OcpiCommandResultStatus.ACCEPTED
    assert result.session_id is not None
    binding = await session_map.get_charger_for_session(result.session_id)
    assert binding is not None
    assert binding.charger_id == CHARGER_ID
    node_id, charger_id, _, command_type, payload, _ = transport.calls[0]
    assert command_type == "RemoteStartTransaction"
    assert payload == {"idTag": "TAG-1", "connectorId": 1}


@pytest.mark.asyncio
async def test_start_session_offline_charger_is_rejected():
    service, presence, transport, session_map, _ = _build_service()

    result = await service.start_session(CHARGER_ID, TENANT_ID, "TAG-1")

    assert result.result == OcpiCommandResultStatus.REJECTED
    assert result.session_id is None


@pytest.mark.asyncio
async def test_start_session_charge_point_rejection_does_not_mint_a_session():
    service, presence, transport, session_map, _ = _build_service()
    await _mark_online(presence)
    transport.set_outcome(CHARGER_ID, CommandOutcome(CommandStatus.REJECTED, {"reason": "no such idTag"}))

    result = await service.start_session(CHARGER_ID, TENANT_ID, "TAG-1")

    assert result.result == OcpiCommandResultStatus.REJECTED
    assert result.session_id is None


@pytest.mark.asyncio
async def test_stop_session_unknown_session_id():
    service, *_ = _build_service()

    result = await service.stop_session("no-such-session", TENANT_ID)

    assert result.result == OcpiCommandResultStatus.UNKNOWN_SESSION


@pytest.mark.asyncio
async def test_stop_session_with_no_active_transaction_is_rejected():
    service, presence, transport, session_map, _ = _build_service()
    await _mark_online(presence)
    session_map.set_binding("SESSION-1", SessionChargerBinding(CHARGER_ID, TENANT_ID, connector_id=1))

    result = await service.stop_session("SESSION-1", TENANT_ID)

    assert result.result == OcpiCommandResultStatus.REJECTED
    assert result.session_id == "SESSION-1"
    assert "no active transaction" in result.reason


@pytest.mark.asyncio
async def test_stop_session_resolves_the_real_ocpp_transaction_id_not_the_ocpi_session_id():
    service, presence, transport, session_map, transaction_repo = _build_service()
    await _mark_online(presence)
    session_map.set_binding("SESSION-1", SessionChargerBinding(CHARGER_ID, TENANT_ID, connector_id=1))
    active_txn = await transaction_repo.start_transaction(
        CHARGER_ID, TENANT_ID, connector_id=1, id_tag="TAG-1", meter_start=0,
        start_timestamp=datetime.now(timezone.utc),
    )
    transport.set_outcome(CHARGER_ID, CommandOutcome(CommandStatus.ACCEPTED, {}))

    result = await service.stop_session("SESSION-1", TENANT_ID)

    assert result.result == OcpiCommandResultStatus.ACCEPTED
    node_id, charger_id, _, command_type, payload, _ = transport.calls[0]
    assert command_type == "RemoteStopTransaction"
    # The dispatched transactionId is OCPP's own transaction id, distinct
    # from the OCPI session_id used to look it up.
    assert payload == {"transactionId": str(active_txn.id)}
    assert payload["transactionId"] != "SESSION-1"


@pytest.mark.asyncio
async def test_reserve_now_dispatches_reservenow_with_expiry_and_token():
    service, presence, transport, *_ = _build_service()
    await _mark_online(presence)
    transport.set_outcome(CHARGER_ID, CommandOutcome(CommandStatus.ACCEPTED, {}))
    expiry = datetime(2026, 8, 1, tzinfo=timezone.utc)

    result = await service.reserve_now(CHARGER_ID, TENANT_ID, "TAG-1", expiry, "RES-1", connector_id=2)

    assert result.result == OcpiCommandResultStatus.ACCEPTED
    node_id, charger_id, _, command_type, payload, _ = transport.calls[0]
    assert command_type == "ReserveNow"
    assert payload["connectorId"] == 2
    assert payload["reservationId"] == "RES-1"
    assert payload["idTag"] == "TAG-1"
    assert payload["expiryDate"] == expiry.isoformat()


@pytest.mark.asyncio
async def test_unlock_connector_dispatches_unlockconnector():
    service, presence, transport, *_ = _build_service()
    await _mark_online(presence)
    transport.set_outcome(CHARGER_ID, CommandOutcome(CommandStatus.ACCEPTED, {}))

    result = await service.unlock_connector(CHARGER_ID, TENANT_ID, connector_id=1)

    assert result.result == OcpiCommandResultStatus.ACCEPTED
    assert transport.calls[0][3] == "UnlockConnector"
    assert transport.calls[0][4] == {"connectorId": 1}


@pytest.mark.asyncio
async def test_cancel_reservation_dispatches_cancelreservation():
    service, presence, transport, *_ = _build_service()
    await _mark_online(presence)
    transport.set_outcome(CHARGER_ID, CommandOutcome(CommandStatus.ACCEPTED, {}))

    result = await service.cancel_reservation(CHARGER_ID, TENANT_ID, "RES-1")

    assert result.result == OcpiCommandResultStatus.ACCEPTED
    assert transport.calls[0][3] == "CancelReservation"
    assert transport.calls[0][4] == {"reservationId": "RES-1"}


@pytest.mark.asyncio
async def test_unlock_connector_offline_charger_is_rejected():
    service, *_ = _build_service()

    result = await service.unlock_connector(CHARGER_ID, TENANT_ID)

    assert result.result == OcpiCommandResultStatus.REJECTED

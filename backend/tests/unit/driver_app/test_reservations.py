import uuid
from datetime import datetime, timedelta, timezone

import pytest

from evagg.driver_app.reservations import DriverReservationService, ReservationError, ReservationNotFoundError
from evagg.ocpi.charging_profiles import InMemorySessionChargerMap
from evagg.ocpi.commands import OcpiCommandService
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
EXPIRES_AT = datetime.now(timezone.utc) + timedelta(hours=1)


def _build_service():
    presence = InMemoryPresenceRegistry()
    transport = FakeCommandTransport()
    command_service = RemoteCommandService(presence, InMemoryCommandLogStore(), transport, InMemoryFirmwareUpdateStore())
    ocpi_command_service = OcpiCommandService(
        InMemorySessionChargerMap(), InMemoryTransactionRepository(), command_service
    )
    return DriverReservationService(ocpi_command_service), presence, transport


async def _mark_online_and_accept(presence, transport, charger_id: str) -> None:
    await presence.mark_online(charger_id, TENANT_ID, node_id="node-a", protocol_version="ocpp1.6", ttl_seconds=600)
    transport.set_outcome(charger_id, CommandOutcome(CommandStatus.ACCEPTED, {"status": "Accepted"}))


@pytest.mark.asyncio
async def test_a_successful_reserve_dispatches_reserve_now_and_returns_the_reservation():
    service, presence, transport = _build_service()
    await _mark_online_and_accept(presence, transport, "CP-001")
    driver_id = uuid.uuid4()

    reservation = await service.reserve("CP-001", 1, EXPIRES_AT, driver_id, TENANT_ID)

    assert reservation.charger_id == "CP-001"
    assert reservation.connector_id == 1
    _node_id, _charger_id, _command_id, command_type, payload, _timeout = transport.calls[-1]
    assert command_type == "ReserveNow"
    assert payload["reservationId"] == reservation.id


@pytest.mark.asyncio
async def test_reserving_on_an_offline_charger_raises():
    service, _, _ = _build_service()  # never marked online

    with pytest.raises(ReservationError):
        await service.reserve("CP-999", 1, EXPIRES_AT, uuid.uuid4(), TENANT_ID)


@pytest.mark.asyncio
async def test_a_rejected_reserve_now_raises_and_creates_no_reservation():
    service, presence, transport = _build_service()
    await presence.mark_online("CP-002", TENANT_ID, node_id="node-a", protocol_version="ocpp1.6", ttl_seconds=600)
    transport.set_outcome("CP-002", CommandOutcome(CommandStatus.REJECTED, {"status": "Rejected"}))
    driver_id = uuid.uuid4()

    with pytest.raises(ReservationError):
        await service.reserve("CP-002", 1, EXPIRES_AT, driver_id, TENANT_ID)

    assert await service.list_for_driver(driver_id) == []


@pytest.mark.asyncio
async def test_list_for_driver_only_returns_that_drivers_reservations():
    service, presence, transport = _build_service()
    await _mark_online_and_accept(presence, transport, "CP-003")
    driver_a = uuid.uuid4()
    driver_b = uuid.uuid4()
    await service.reserve("CP-003", 1, EXPIRES_AT, driver_a, TENANT_ID)
    await service.reserve("CP-003", 2, EXPIRES_AT, driver_b, TENANT_ID)

    reservations_a = await service.list_for_driver(driver_a)

    assert len(reservations_a) == 1
    assert reservations_a[0].connector_id == 1


@pytest.mark.asyncio
async def test_cancel_dispatches_cancel_reservation_and_removes_it():
    service, presence, transport = _build_service()
    await _mark_online_and_accept(presence, transport, "CP-004")
    driver_id = uuid.uuid4()
    reservation = await service.reserve("CP-004", 1, EXPIRES_AT, driver_id, TENANT_ID)

    await service.cancel(reservation.id, driver_id, TENANT_ID)

    _node_id, _charger_id, _command_id, command_type, payload, _timeout = transport.calls[-1]
    assert command_type == "CancelReservation"
    assert payload["reservationId"] == reservation.id
    assert await service.list_for_driver(driver_id) == []


@pytest.mark.asyncio
async def test_cancel_by_a_different_driver_is_refused():
    service, presence, transport = _build_service()
    await _mark_online_and_accept(presence, transport, "CP-005")
    owner_id = uuid.uuid4()
    reservation = await service.reserve("CP-005", 1, EXPIRES_AT, owner_id, TENANT_ID)

    with pytest.raises(ReservationNotFoundError):
        await service.cancel(reservation.id, uuid.uuid4(), TENANT_ID)

    # Still cancellable by its actual owner afterwards — the failed attempt
    # didn't corrupt any state.
    await service.cancel(reservation.id, owner_id, TENANT_ID)


@pytest.mark.asyncio
async def test_cancel_of_an_unknown_reservation_raises_not_found():
    service, _, _ = _build_service()

    with pytest.raises(ReservationNotFoundError):
        await service.cancel("no-such-reservation", uuid.uuid4(), TENANT_ID)

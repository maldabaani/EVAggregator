from __future__ import annotations

import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from evagg.billing.payment_methods import DIRECT_CARD, InMemoryPaymentMethodStore, PaymentMethod
from evagg.charging_auth.autocharge import InMemoryAutochargeMacStore
from evagg.charging_auth.plug_and_charge import InMemoryEmaidDriverMap, PlugAndChargeValidator
from evagg.charging_auth.qr_token import sign_qr_token
from evagg.charging_auth.session_start import SessionNotFoundError, SessionStartError, SessionStartService
from evagg.ocpi.charging_profiles import InMemorySessionChargerMap
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
from charging_auth.x509_test_helpers import make_ca_cert, make_leaf_cert, pem

SECRET = "shared-gateway-secret"
TENANT_ID = uuid.uuid4()


def _build_command_service():
    presence = InMemoryPresenceRegistry()
    transport = FakeCommandTransport()
    command_service = RemoteCommandService(presence, InMemoryCommandLogStore(), transport, InMemoryFirmwareUpdateStore())
    return command_service, presence, transport


async def _mark_online_and_accept(presence, transport, charger_id: str) -> None:
    await presence.mark_online(charger_id, TENANT_ID, node_id="node-a", protocol_version="ocpp1.6", ttl_seconds=600)
    transport.set_outcome(charger_id, CommandOutcome(CommandStatus.ACCEPTED, {"status": "Accepted"}))


def _build_service(
    payment_methods=None,
    wallet_id_for_driver=None,
    command_service=None,
    session_charger_map=None,
    transaction_repository=None,
):
    return SessionStartService(
        payment_method_store=payment_methods or InMemoryPaymentMethodStore(),
        wallet_id_for_driver=wallet_id_for_driver or (lambda driver_id: driver_id),
        command_service=command_service or _build_command_service()[0],
        session_charger_map=session_charger_map or InMemorySessionChargerMap(),
        transaction_repository=transaction_repository or InMemoryTransactionRepository(),
    )


@pytest.mark.asyncio
async def test_all_four_methods_correctly_hook_up_default_payment_method():
    qr_driver_id = uuid.uuid4()
    autocharge_driver_id = uuid.uuid4()
    plug_and_charge_driver_id = uuid.uuid4()
    app_driver_id = uuid.uuid4()

    wallet_ids = {
        qr_driver_id: uuid.uuid4(),
        autocharge_driver_id: uuid.uuid4(),
        plug_and_charge_driver_id: uuid.uuid4(),
        app_driver_id: uuid.uuid4(),
    }
    payment_methods = InMemoryPaymentMethodStore()
    expected_methods = {}
    for driver_id, wallet_id in wallet_ids.items():
        method = PaymentMethod(id=uuid.uuid4(), wallet_id=wallet_id, type=DIRECT_CARD, psp_token=f"tok-{driver_id}", is_default=True)
        payment_methods.add(method)
        expected_methods[driver_id] = method

    command_service, presence, transport = _build_command_service()
    for charger_id in ("CP-001", "CP-002", "CP-003", "CP-004"):
        await _mark_online_and_accept(presence, transport, charger_id)
    service = _build_service(
        payment_methods=payment_methods, wallet_id_for_driver=lambda driver_id: wallet_ids[driver_id],
        command_service=command_service,
    )

    # QR
    qr_token = sign_qr_token("CP-001", 1, SECRET, issued_at=1_000_000.0)
    qr_result = await service.start_via_qr(qr_token, qr_driver_id, SECRET, TENANT_ID, now=1_000_010.0)
    assert qr_result.payment_method == expected_methods[qr_driver_id]

    # Autocharge
    mac_store = InMemoryAutochargeMacStore()
    mac_store.register("AA:BB:CC:DD:EE:FF", autocharge_driver_id)
    autocharge_result = await service.start_via_autocharge("AA:BB:CC:DD:EE:FF", "CP-002", TENANT_ID, mac_store)
    assert autocharge_result.payment_method == expected_methods[autocharge_driver_id]

    # Plug & Charge
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_cert = make_ca_cert(ca_key)
    vehicle_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    emaid_map = InMemoryEmaidDriverMap()
    emaid_map.register("EMAID-XYZ", plug_and_charge_driver_id)
    validator = PlugAndChargeValidator([pem(ca_cert)], emaid_map)
    cert = make_leaf_cert(ca_key, ca_cert, vehicle_key.public_key(), emaid="EMAID-XYZ")
    pnc_result = await service.start_via_plug_and_charge(pem(cert), "CP-003", TENANT_ID, validator)
    assert pnc_result.payment_method == expected_methods[plug_and_charge_driver_id]

    # App (the mobile "Start Charging" button)
    app_result = await service.start_via_app("CP-004", 1, app_driver_id, TENANT_ID)
    assert app_result.payment_method == expected_methods[app_driver_id]

    # All four resolved a different driver's own default method, never mixed up.
    assert len({
        qr_result.payment_method.wallet_id, autocharge_result.payment_method.wallet_id,
        pnc_result.payment_method.wallet_id, app_result.payment_method.wallet_id,
    }) == 4


@pytest.mark.asyncio
async def test_a_successful_start_actually_dispatches_remote_start_transaction():
    command_service, presence, transport = _build_command_service()
    await _mark_online_and_accept(presence, transport, "CP-004")
    service = _build_service(command_service=command_service)

    result = await service.start_via_app("CP-004", 2, uuid.uuid4(), TENANT_ID)

    _node_id, _charger_id, _command_id, command_type, payload, _timeout = transport.calls[-1]
    assert command_type == "RemoteStartTransaction"
    assert payload["connectorId"] == 2
    assert payload["idTag"] == result.id_tag


@pytest.mark.asyncio
async def test_a_successful_start_records_a_session_binding_resolvable_later():
    command_service, presence, transport = _build_command_service()
    await _mark_online_and_accept(presence, transport, "CP-004")
    session_charger_map = InMemorySessionChargerMap()
    service = _build_service(command_service=command_service, session_charger_map=session_charger_map)

    result = await service.start_via_app("CP-004", 2, uuid.uuid4(), TENANT_ID)

    binding = await session_charger_map.get_charger_for_session(result.session_id)
    assert binding is not None
    assert binding.charger_id == "CP-004"
    assert binding.connector_id == 2
    assert binding.tenant_id == TENANT_ID


@pytest.mark.asyncio
async def test_starting_a_session_on_an_offline_charger_raises_and_creates_no_binding():
    session_charger_map = InMemorySessionChargerMap()
    service = _build_service(session_charger_map=session_charger_map)  # charger never marked online

    with pytest.raises(SessionStartError):
        await service.start_via_app("CP-999", 1, uuid.uuid4(), TENANT_ID)

    assert await session_charger_map.get_charger_for_session("whatever") is None


@pytest.mark.asyncio
async def test_a_rejected_remote_start_command_raises_and_creates_no_binding():
    command_service, presence, transport = _build_command_service()
    await presence.mark_online("CP-005", TENANT_ID, node_id="node-a", protocol_version="ocpp1.6", ttl_seconds=600)
    transport.set_outcome("CP-005", CommandOutcome(CommandStatus.REJECTED, {"status": "Rejected"}))
    session_charger_map = InMemorySessionChargerMap()
    service = _build_service(command_service=command_service, session_charger_map=session_charger_map)

    with pytest.raises(SessionStartError):
        await service.start_via_app("CP-005", 1, uuid.uuid4(), TENANT_ID)


@pytest.mark.asyncio
async def test_get_session_status_reports_active_true_once_the_charger_reports_a_transaction():
    from datetime import datetime, timezone

    command_service, presence, transport = _build_command_service()
    await _mark_online_and_accept(presence, transport, "CP-006")
    transaction_repository = InMemoryTransactionRepository()
    service = _build_service(command_service=command_service, transaction_repository=transaction_repository)
    driver_id = uuid.uuid4()

    result = await service.start_via_app("CP-006", 1, driver_id, TENANT_ID)
    status_before = await service.get_session_status(result.session_id, driver_id)
    assert status_before.active is False

    await transaction_repository.start_transaction(
        "CP-006", TENANT_ID, 1, result.id_tag, meter_start=0, start_timestamp=datetime.now(timezone.utc)
    )
    status_after = await service.get_session_status(result.session_id, driver_id)
    assert status_after.active is True
    assert status_after.charger_id == "CP-006"
    assert status_after.connector_id == 1


@pytest.mark.asyncio
async def test_get_session_status_for_an_unknown_session_raises_not_found():
    service = _build_service()

    with pytest.raises(SessionNotFoundError):
        await service.get_session_status("no-such-session", uuid.uuid4())


@pytest.mark.asyncio
async def test_get_session_status_refuses_a_driver_who_is_not_the_session_owner():
    command_service, presence, transport = _build_command_service()
    await _mark_online_and_accept(presence, transport, "CP-007")
    service = _build_service(command_service=command_service)
    owner_id = uuid.uuid4()
    result = await service.start_via_app("CP-007", 1, owner_id, TENANT_ID)

    with pytest.raises(SessionNotFoundError):
        await service.get_session_status(result.session_id, uuid.uuid4())


@pytest.mark.asyncio
async def test_stop_session_dispatches_remote_stop_transaction_for_the_active_transaction():
    from datetime import datetime, timezone

    command_service, presence, transport = _build_command_service()
    await _mark_online_and_accept(presence, transport, "CP-008")
    transaction_repository = InMemoryTransactionRepository()
    service = _build_service(command_service=command_service, transaction_repository=transaction_repository)
    driver_id = uuid.uuid4()
    result = await service.start_via_app("CP-008", 1, driver_id, TENANT_ID)
    active_txn = await transaction_repository.start_transaction(
        "CP-008", TENANT_ID, 1, result.id_tag, meter_start=0, start_timestamp=datetime.now(timezone.utc)
    )

    await service.stop_session(result.session_id, driver_id, TENANT_ID)

    _node_id, _charger_id, _command_id, command_type, payload, _timeout = transport.calls[-1]
    assert command_type == "RemoteStopTransaction"
    assert payload["transactionId"] == str(active_txn.id)


@pytest.mark.asyncio
async def test_stop_session_with_no_active_transaction_raises():
    command_service, presence, transport = _build_command_service()
    await _mark_online_and_accept(presence, transport, "CP-009")
    service = _build_service(command_service=command_service)
    driver_id = uuid.uuid4()
    result = await service.start_via_app("CP-009", 1, driver_id, TENANT_ID)
    # No StartTransaction.req has arrived from the charger yet — no active transaction to stop.

    with pytest.raises(SessionStartError):
        await service.stop_session(result.session_id, driver_id, TENANT_ID)


@pytest.mark.asyncio
async def test_stop_session_refuses_a_driver_who_is_not_the_session_owner():
    command_service, presence, transport = _build_command_service()
    await _mark_online_and_accept(presence, transport, "CP-010")
    service = _build_service(command_service=command_service)
    owner_id = uuid.uuid4()
    result = await service.start_via_app("CP-010", 1, owner_id, TENANT_ID)

    with pytest.raises(SessionNotFoundError):
        await service.stop_session(result.session_id, uuid.uuid4(), TENANT_ID)

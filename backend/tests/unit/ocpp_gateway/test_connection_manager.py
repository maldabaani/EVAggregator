"""Task 2.1 unit tests — all isolated (in-memory presence/credentials/
transactions/events, no network or real sockets). End-to-end verification
against a real OCPP charger simulator (connect -> boot -> heartbeat ->
disconnect -> reconnect-with-active-transaction) is tracked separately as an
integration test, per the backlog's own note that this closes a previously
flagged verification gap — not covered here.
"""

from __future__ import annotations

import uuid

import pytest

from evagg.ocpp_gateway.connection_manager import ConnectionManager, resolve_handler_codepath
from evagg.ocpp_gateway.credentials import InMemoryCredentialVerifier
from evagg.ocpp_gateway.events import InMemoryEventPublisher
from evagg.ocpp_gateway.presence import InMemoryPresenceRegistry
from evagg.ocpp_gateway.registration import InMemoryChargerRegistry
from evagg.ocpp_gateway.transactions import ActiveTransaction, InMemoryTransactionRepository

TENANT_ID = uuid.uuid4()
CHARGER_ID = "CP-001"


def _build_manager(heartbeat_interval: int = 300):
    presence = InMemoryPresenceRegistry()
    credentials = InMemoryCredentialVerifier({CHARGER_ID: "s3cret"})
    transactions = InMemoryTransactionRepository()
    charger_registry = InMemoryChargerRegistry()
    events = InMemoryEventPublisher()
    manager = ConnectionManager(
        presence=presence,
        credentials=credentials,
        transactions=transactions,
        charger_registry=charger_registry,
        events=events,
        node_id="node-a",
        default_heartbeat_interval_seconds=heartbeat_interval,
    )
    return manager, presence, credentials, transactions, charger_registry, events


@pytest.mark.asyncio
async def test_valid_handshake_creates_presence_entry():
    manager, presence, *_ = _build_manager()

    result = await manager.handle_handshake(CHARGER_ID, TENANT_ID, "s3cret", "ocpp1.6")

    assert result.accepted
    state = await presence.get(CHARGER_ID)
    assert state is not None
    assert state.status == "online"
    assert state.protocol_version == "ocpp1.6"
    assert state.tenant_id == str(TENANT_ID)


@pytest.mark.asyncio
async def test_missed_heartbeats_marks_charger_offline():
    manager, presence, *_, events = _build_manager(heartbeat_interval=60)
    await manager.handle_handshake(CHARGER_ID, TENANT_ID, "s3cret", "ocpp1.6")

    # Simulate time passing well beyond 2x the heartbeat interval (120s).
    far_future = (await presence.get(CHARGER_ID)).last_seen + 121

    newly_offline = await manager.check_and_expire_heartbeats([CHARGER_ID], heartbeat_interval_seconds=60, now=far_future)

    assert newly_offline == [CHARGER_ID]
    state = await presence.get(CHARGER_ID)
    assert state.status == "offline"
    assert events.published == [(TENANT_ID, CHARGER_ID)]


@pytest.mark.asyncio
async def test_missed_heartbeats_does_not_flag_charger_within_window():
    manager, presence, *_ = _build_manager(heartbeat_interval=60)
    await manager.handle_handshake(CHARGER_ID, TENANT_ID, "s3cret", "ocpp1.6")
    recent = (await presence.get(CHARGER_ID)).last_seen + 30  # well within 120s TTL

    newly_offline = await manager.check_and_expire_heartbeats([CHARGER_ID], heartbeat_interval_seconds=60, now=recent)

    assert newly_offline == []


@pytest.mark.asyncio
async def test_reconnect_within_ttl_resumes_active_transaction():
    manager, presence, credentials, transactions, *_ = _build_manager()
    await manager.handle_handshake(CHARGER_ID, TENANT_ID, "s3cret", "ocpp1.6")
    active_txn = ActiveTransaction(id=uuid.uuid4(), charger_id=CHARGER_ID, connector_id=1, id_tag="TAG-1")
    transactions.seed_active_transaction(CHARGER_ID, active_txn)

    # Reconnect while presence is still "online" (i.e. within the TTL window).
    result = await manager.handle_reconnect(CHARGER_ID, TENANT_ID, "s3cret", "ocpp1.6")

    assert result.handshake.accepted
    assert result.resumed_transaction == active_txn


@pytest.mark.asyncio
async def test_reconnect_after_ttl_does_not_falsely_resume():
    manager, presence, credentials, transactions, *_ = _build_manager()
    active_txn = ActiveTransaction(id=uuid.uuid4(), charger_id=CHARGER_ID, connector_id=1, id_tag="TAG-1")
    transactions.seed_active_transaction(CHARGER_ID, active_txn)

    # No prior handshake at all -> no presence entry -> reconnect looks like
    # it's arriving after the TTL window (or for the first time).
    result = await manager.handle_reconnect(CHARGER_ID, TENANT_ID, "s3cret", "ocpp1.6")

    assert result.handshake.accepted
    assert result.resumed_transaction is None


@pytest.mark.asyncio
async def test_reconnect_after_marked_offline_does_not_falsely_resume():
    manager, presence, credentials, transactions, charger_registry, events = _build_manager(heartbeat_interval=60)
    await manager.handle_handshake(CHARGER_ID, TENANT_ID, "s3cret", "ocpp1.6")
    active_txn = ActiveTransaction(id=uuid.uuid4(), charger_id=CHARGER_ID, connector_id=1, id_tag="TAG-1")
    transactions.seed_active_transaction(CHARGER_ID, active_txn)

    far_future = (await presence.get(CHARGER_ID)).last_seen + 121
    await manager.check_and_expire_heartbeats([CHARGER_ID], heartbeat_interval_seconds=60, now=far_future)

    result = await manager.handle_reconnect(CHARGER_ID, TENANT_ID, "s3cret", "ocpp1.6")

    assert result.resumed_transaction is None


@pytest.mark.asyncio
async def test_invalid_credentials_rejects_handshake():
    manager, presence, *_ = _build_manager()

    result = await manager.handle_handshake(CHARGER_ID, TENANT_ID, "wrong-secret", "ocpp1.6")

    assert not result.accepted
    assert result.reason == "invalid credentials"
    assert await presence.get(CHARGER_ID) is None


@pytest.mark.asyncio
async def test_duplicate_boot_notification_is_idempotent():
    manager, *_ = _build_manager()

    first = await manager.handle_boot_notification(CHARGER_ID, TENANT_ID, "Vendor", "Model-X", "1.0.0")
    second = await manager.handle_boot_notification(CHARGER_ID, TENANT_ID, "Vendor", "Model-X", "1.0.1")

    assert first.is_new_charger
    assert not second.is_new_charger
    assert second.status == first.status  # registration status untouched by re-boot


@pytest.mark.asyncio
async def test_subprotocol_header_routes_to_correct_handler():
    assert resolve_handler_codepath("ocpp1.6") == "ocpp1.6"
    assert resolve_handler_codepath("ocpp2.0.1") == "ocpp2.0.1"
    assert resolve_handler_codepath("mqtt") is None
    assert resolve_handler_codepath(None) is None


@pytest.mark.asyncio
async def test_unsupported_subprotocol_rejects_handshake_before_credential_check():
    manager, presence, *_ = _build_manager()

    result = await manager.handle_handshake(CHARGER_ID, TENANT_ID, "s3cret", "mqtt")

    assert not result.accepted
    assert result.reason == "unsupported subprotocol"
    assert await presence.get(CHARGER_ID) is None

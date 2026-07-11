"""Task 2.2 unit tests — all isolated (in-memory fakes, no network/DB).
Load testing (500 concurrent sessions emitting MeterValues, p99 latency /
zero-drop assertions) is tracked separately, per the backlog's own note.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from evagg.ocpp_gateway.authorize import AuthStatus, Authorizer, InMemoryLocalIdTagStore, InMemoryRoamingTokenChecker
from evagg.ocpp_gateway.connectors import InMemoryConnectorStore
from evagg.ocpp_gateway.events import InMemoryEventPublisher
from evagg.ocpp_gateway.meter_values import InMemoryMeterValueSink, MeterValueBuffer
from evagg.ocpp_gateway.message_handlers import OcppMessageHandlers
from evagg.ocpp_gateway.registration import InMemoryChargerRegistry
from evagg.ocpp_gateway.transactions import InMemoryTransactionRepository

TENANT_ID = uuid.uuid4()
CHARGER_ID = "CP-001"


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _build_handlers(clock=None, max_batch_size: int = 50, flush_interval_seconds: float = 2.0):
    charger_registry = InMemoryChargerRegistry()
    connector_store = InMemoryConnectorStore()
    local_store = InMemoryLocalIdTagStore()
    roaming_checker = InMemoryRoamingTokenChecker()
    authorizer = Authorizer(local_store, roaming_checker)
    transactions = InMemoryTransactionRepository()
    sink = InMemoryMeterValueSink()
    buffer = MeterValueBuffer(
        sink,
        max_batch_size=max_batch_size,
        flush_interval_seconds=flush_interval_seconds,
        clock=clock or (lambda: 0.0),
    )
    events = InMemoryEventPublisher()
    handlers = OcppMessageHandlers(charger_registry, connector_store, authorizer, transactions, buffer, events)
    return handlers, charger_registry, connector_store, local_store, roaming_checker, transactions, sink, buffer, events


@pytest.mark.asyncio
async def test_boot_notification_unregistered_charger_returns_pending():
    handlers, *_ = _build_handlers()

    response = await handlers.handle_boot_notification(CHARGER_ID, TENANT_ID, "Vendor", "Model-X", "1.0.0")

    assert response.status == "Pending"


@pytest.mark.asyncio
async def test_boot_notification_idempotent_on_duplicate():
    handlers, charger_registry, *_ = _build_handlers()
    first_response = await handlers.handle_boot_notification(CHARGER_ID, TENANT_ID, "Vendor", "Model-X", "1.0.0")
    assert first_response.status == "Pending"

    # An admin approves the charger in the portal (Task 2.2's registration flow).
    charger_registry.set_status(CHARGER_ID, "accepted")

    second_response = await handlers.handle_boot_notification(CHARGER_ID, TENANT_ID, "Vendor", "Model-X", "1.0.1")

    assert second_response.status == "Accepted"  # duplicate boot doesn't reset registration status


@pytest.mark.asyncio
async def test_status_notification_updates_connector_and_publishes_event():
    handlers, _, connector_store, *_ , events = _build_handlers()

    await handlers.handle_status_notification(CHARGER_ID, TENANT_ID, 1, "Faulted", "GroundFailure")

    status = await connector_store.get_status(CHARGER_ID, 1)
    assert status is not None
    assert status.status == "Faulted"
    assert status.error_code == "GroundFailure"
    assert events.status_notifications == [(TENANT_ID, CHARGER_ID, 1, "Faulted", "GroundFailure")]


@pytest.mark.asyncio
async def test_authorize_blocked_id_tag_returns_blocked():
    handlers, _, _, local_store, *_ = _build_handlers()
    local_store.set_status("TAG-BLOCKED", AuthStatus.BLOCKED)

    status = await handlers.handle_authorize("TAG-BLOCKED")

    assert status == AuthStatus.BLOCKED


@pytest.mark.asyncio
async def test_authorize_blocked_tag_prevents_transaction_start():
    handlers, *_ = _build_handlers()
    local_store = handlers._authorizer._local_store
    local_store.set_status("TAG-BLOCKED", AuthStatus.BLOCKED)

    response = await handlers.handle_start_transaction(
        CHARGER_ID, TENANT_ID, 1, "TAG-BLOCKED", meter_start=0, start_timestamp=datetime.now(timezone.utc)
    )

    assert response.id_tag_status == AuthStatus.BLOCKED.value


@pytest.mark.asyncio
async def test_authorize_falls_back_to_ocpi_token_for_unknown_local_tag():
    handlers, _, _, local_store, roaming_checker, *_ = _build_handlers()
    roaming_checker.set_status("ROAMING-TAG", AuthStatus.ACCEPTED)

    status = await handlers.handle_authorize("ROAMING-TAG")

    assert status == AuthStatus.ACCEPTED
    assert roaming_checker.checked_tags == ["ROAMING-TAG"]


@pytest.mark.asyncio
async def test_authorize_does_not_call_roaming_when_known_locally():
    handlers, _, _, local_store, roaming_checker, *_ = _build_handlers()
    local_store.set_status("LOCAL-TAG", AuthStatus.ACCEPTED)

    status = await handlers.handle_authorize("LOCAL-TAG")

    assert status == AuthStatus.ACCEPTED
    assert roaming_checker.checked_tags == []


@pytest.mark.asyncio
async def test_start_transaction_creates_active_transaction_record():
    handlers, _, _, local_store, _, transactions, *_ = _build_handlers()
    local_store.set_status("TAG-1", AuthStatus.ACCEPTED)

    response = await handlers.handle_start_transaction(
        CHARGER_ID, TENANT_ID, 1, "TAG-1", meter_start=1000, start_timestamp=datetime.now(timezone.utc)
    )

    assert response.id_tag_status == "Accepted"
    active = await transactions.get_active_transaction(CHARGER_ID)
    assert active is not None
    assert active.id == response.transaction_id
    assert active.id_tag == "TAG-1"


@pytest.mark.asyncio
async def test_stop_transaction_is_idempotent_on_retry():
    handlers, _, _, local_store, _, transactions, _, _, events = _build_handlers()
    local_store.set_status("TAG-1", AuthStatus.ACCEPTED)
    start_response = await handlers.handle_start_transaction(
        CHARGER_ID, TENANT_ID, 1, "TAG-1", meter_start=1000, start_timestamp=datetime.now(timezone.utc)
    )

    first_stop = await handlers.handle_stop_transaction(
        start_response.transaction_id, meter_stop=1500, stop_timestamp=datetime.now(timezone.utc), reason="Local"
    )
    second_stop = await handlers.handle_stop_transaction(
        start_response.transaction_id, meter_stop=1500, stop_timestamp=datetime.now(timezone.utc), reason="Local"
    )

    assert first_stop.id_tag_status == "Accepted"
    assert second_stop.id_tag_status == "Accepted"
    # Exactly one stop_transaction event published, even though the charger retried.
    assert len(events.stop_transactions) == 1


@pytest.mark.asyncio
async def test_meter_values_batched_write_flushes_on_size_threshold():
    handlers, _, _, local_store, _, _, sink, buffer, _ = _build_handlers(max_batch_size=3, flush_interval_seconds=1000)
    ts = datetime.now(timezone.utc)
    txn_id = uuid.uuid4()

    await handlers.handle_meter_values(TENANT_ID, txn_id, CHARGER_ID, ts, [("Energy.Active.Import.Register", 1.0, "kWh")])
    await handlers.handle_meter_values(TENANT_ID, txn_id, CHARGER_ID, ts, [("Energy.Active.Import.Register", 2.0, "kWh")])
    assert sink.batches == []  # below threshold, not flushed yet

    await handlers.handle_meter_values(TENANT_ID, txn_id, CHARGER_ID, ts, [("Energy.Active.Import.Register", 3.0, "kWh")])

    assert len(sink.batches) == 1
    assert len(sink.batches[0]) == 3


@pytest.mark.asyncio
async def test_meter_values_batched_write_flushes_on_time_threshold():
    clock = _FakeClock()
    handlers, _, _, _, _, _, sink, buffer, _ = _build_handlers(clock=clock, max_batch_size=50, flush_interval_seconds=2.0)
    ts = datetime.now(timezone.utc)
    txn_id = uuid.uuid4()

    await handlers.handle_meter_values(TENANT_ID, txn_id, CHARGER_ID, ts, [("Power.Active.Import", 7.0, "W")])
    assert sink.batches == []

    clock.advance(2.1)
    await handlers.handle_meter_values(TENANT_ID, txn_id, CHARGER_ID, ts, [("Power.Active.Import", 8.0, "W")])

    assert len(sink.batches) == 1
    assert len(sink.batches[0]) == 2


@pytest.mark.asyncio
async def test_stop_transaction_flushes_trailing_meter_values():
    handlers, _, _, local_store, _, _, sink, buffer, _ = _build_handlers(max_batch_size=50, flush_interval_seconds=1000)
    local_store.set_status("TAG-1", AuthStatus.ACCEPTED)
    ts = datetime.now(timezone.utc)
    start_response = await handlers.handle_start_transaction(
        CHARGER_ID, TENANT_ID, 1, "TAG-1", meter_start=0, start_timestamp=ts
    )
    await handlers.handle_meter_values(
        TENANT_ID, start_response.transaction_id, CHARGER_ID, ts, [("Energy.Active.Import.Register", 5.0, "kWh")]
    )
    assert sink.batches == []  # buffered, below threshold

    await handlers.handle_stop_transaction(start_response.transaction_id, meter_stop=500, stop_timestamp=ts)

    assert len(sink.batches) == 1  # flushed on session close, not left stranded

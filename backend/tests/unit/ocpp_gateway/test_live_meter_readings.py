import uuid
from datetime import datetime, timedelta, timezone

import pytest

from evagg.ocpp_gateway.live_meter_readings import InMemoryLatestMeterReadingStore
from evagg.ocpp_gateway.meter_values import MeterReading

TENANT_ID = uuid.uuid4()
CHARGER_ID = "CP-001"


def _reading(transaction_id: uuid.UUID, measurand: str, value: float, ts: datetime) -> MeterReading:
    return MeterReading(TENANT_ID, transaction_id, CHARGER_ID, ts, measurand, value, "kWh")


@pytest.mark.asyncio
async def test_an_unknown_transaction_has_no_latest_reading():
    store = InMemoryLatestMeterReadingStore()

    assert await store.get_latest(uuid.uuid4(), "Energy.Active.Import.Register") is None


@pytest.mark.asyncio
async def test_a_new_reading_becomes_the_latest():
    store = InMemoryLatestMeterReadingStore()
    txn_id = uuid.uuid4()
    ts = datetime.now(timezone.utc)

    await store.update(_reading(txn_id, "Energy.Active.Import.Register", 1.0, ts))
    await store.update(_reading(txn_id, "Energy.Active.Import.Register", 2.0, ts + timedelta(seconds=1)))

    latest = await store.get_latest(txn_id, "Energy.Active.Import.Register")
    assert latest is not None
    assert latest.value == 2.0


@pytest.mark.asyncio
async def test_an_out_of_order_older_reading_does_not_overwrite_the_latest():
    store = InMemoryLatestMeterReadingStore()
    txn_id = uuid.uuid4()
    ts = datetime.now(timezone.utc)

    await store.update(_reading(txn_id, "Energy.Active.Import.Register", 2.0, ts + timedelta(seconds=1)))
    await store.update(_reading(txn_id, "Energy.Active.Import.Register", 1.0, ts))  # arrives late/out of order

    latest = await store.get_latest(txn_id, "Energy.Active.Import.Register")
    assert latest is not None
    assert latest.value == 2.0


@pytest.mark.asyncio
async def test_different_measurands_are_tracked_independently():
    store = InMemoryLatestMeterReadingStore()
    txn_id = uuid.uuid4()
    ts = datetime.now(timezone.utc)

    await store.update(_reading(txn_id, "Energy.Active.Import.Register", 4.2, ts))
    await store.update(_reading(txn_id, "Power.Active.Import", 7.5, ts))

    energy = await store.get_latest(txn_id, "Energy.Active.Import.Register")
    power = await store.get_latest(txn_id, "Power.Active.Import")
    assert energy is not None and energy.value == 4.2
    assert power is not None and power.value == 7.5


@pytest.mark.asyncio
async def test_different_transactions_are_tracked_independently():
    store = InMemoryLatestMeterReadingStore()
    txn_a, txn_b = uuid.uuid4(), uuid.uuid4()
    ts = datetime.now(timezone.utc)

    await store.update(_reading(txn_a, "Energy.Active.Import.Register", 1.0, ts))
    await store.update(_reading(txn_b, "Energy.Active.Import.Register", 9.0, ts))

    assert (await store.get_latest(txn_a, "Energy.Active.Import.Register")).value == 1.0
    assert (await store.get_latest(txn_b, "Energy.Active.Import.Register")).value == 9.0

import uuid
from datetime import datetime, timezone

import pytest

from evagg.ocpp_gateway.meter_values import MeterReading
from evagg.ocpp_gateway.transactions import UnknownTransactionError
from evagg.persistence.supabase_client import SupabaseRestClient
from evagg.persistence.supabase_ocpp import (
    SupabaseChargerRegistry,
    SupabaseConnectorStore,
    SupabaseCredentialVerifier,
    SupabaseMeterValueSink,
    SupabaseTransactionRepository,
)

from .fake_postgrest import build_client_with_fake

TENANT_ID = uuid.uuid4()


@pytest.mark.asyncio
async def test_charger_registry_first_boot_is_pending_and_new():
    client, _ = build_client_with_fake(SupabaseRestClient)
    registry = SupabaseChargerRegistry(client)

    result = await registry.upsert_on_boot("charger-1", TENANT_ID, "Acme", "X1", "1.0")

    assert result.status == "pending"
    assert result.is_new_charger is True


@pytest.mark.asyncio
async def test_charger_registry_second_boot_refreshes_but_keeps_status():
    client, fake = build_client_with_fake(SupabaseRestClient)
    registry = SupabaseChargerRegistry(client)
    await registry.upsert_on_boot("charger-1", TENANT_ID, "Acme", "X1", "1.0")

    # Simulate an admin approving the charger between boots.
    fake.tables["charger"][0]["status"] = "accepted"

    result = await registry.upsert_on_boot("charger-1", TENANT_ID, "Acme", "X2", "1.1")

    assert result.status == "accepted"
    assert result.is_new_charger is False
    assert fake.tables["charger"][0]["model"] == "X2"


@pytest.mark.asyncio
async def test_credential_verifier_round_trip():
    client, _ = build_client_with_fake(SupabaseRestClient)
    registry = SupabaseChargerRegistry(client)
    await registry.upsert_on_boot("charger-1", TENANT_ID, None, None, None)

    verifier = SupabaseCredentialVerifier(client)
    await verifier.set_credential("charger-1", "s3cret")

    assert await verifier.verify("charger-1", "s3cret") is True
    assert await verifier.verify("charger-1", "wrong") is False


@pytest.mark.asyncio
async def test_credential_verifier_unknown_charger_rejected():
    client, _ = build_client_with_fake(SupabaseRestClient)
    verifier = SupabaseCredentialVerifier(client)
    assert await verifier.verify("no-such-charger", "anything") is False


@pytest.mark.asyncio
async def test_connector_store_update_then_get():
    client, _ = build_client_with_fake(SupabaseRestClient)
    await SupabaseChargerRegistry(client).upsert_on_boot("charger-1", TENANT_ID, None, None, None)

    store = SupabaseConnectorStore(client)
    await store.update_status("charger-1", 1, "Charging", None)

    status = await store.get_status("charger-1", 1)
    assert status.status == "Charging"
    assert status.charger_id == "charger-1"
    assert status.connector_id == 1


@pytest.mark.asyncio
async def test_connector_store_upsert_overwrites_existing_status():
    client, _ = build_client_with_fake(SupabaseRestClient)
    await SupabaseChargerRegistry(client).upsert_on_boot("charger-1", TENANT_ID, None, None, None)
    store = SupabaseConnectorStore(client)

    await store.update_status("charger-1", 1, "Available", None)
    await store.update_status("charger-1", 1, "Faulted", "HighTemperature")

    status = await store.get_status("charger-1", 1)
    assert status.status == "Faulted"
    assert status.error_code == "HighTemperature"


@pytest.mark.asyncio
async def test_connector_store_unknown_charger_returns_none():
    client, _ = build_client_with_fake(SupabaseRestClient)
    store = SupabaseConnectorStore(client)
    assert await store.get_status("no-such-charger", 1) is None


@pytest.mark.asyncio
async def test_transaction_lifecycle_start_then_stop():
    client, _ = build_client_with_fake(SupabaseRestClient)
    await SupabaseChargerRegistry(client).upsert_on_boot("charger-1", TENANT_ID, None, None, None)
    repo = SupabaseTransactionRepository(client)

    txn = await repo.start_transaction(
        "charger-1", TENANT_ID, connector_id=1, id_tag="TAG-1", meter_start=1000,
        start_timestamp=datetime.now(timezone.utc),
    )
    assert txn.charger_id == "charger-1"

    active = await repo.get_active_transaction("charger-1")
    assert active is not None
    assert active.id == txn.id

    result = await repo.stop_transaction(txn.id, meter_stop=2000, stop_timestamp=datetime.now(timezone.utc), reason="Local")
    assert result.already_stopped is False
    assert result.charger_id == "charger-1"
    assert result.tenant_id == TENANT_ID


@pytest.mark.asyncio
async def test_stop_transaction_twice_is_idempotent():
    client, _ = build_client_with_fake(SupabaseRestClient)
    await SupabaseChargerRegistry(client).upsert_on_boot("charger-1", TENANT_ID, None, None, None)
    repo = SupabaseTransactionRepository(client)
    txn = await repo.start_transaction(
        "charger-1", TENANT_ID, connector_id=1, id_tag="TAG-1", meter_start=1000,
        start_timestamp=datetime.now(timezone.utc),
    )

    first = await repo.stop_transaction(txn.id, meter_stop=2000, stop_timestamp=datetime.now(timezone.utc), reason=None)
    second = await repo.stop_transaction(txn.id, meter_stop=2000, stop_timestamp=datetime.now(timezone.utc), reason=None)

    assert first.already_stopped is False
    assert second.already_stopped is True
    assert second.charger_id == "charger-1"


@pytest.mark.asyncio
async def test_stop_unknown_transaction_raises():
    client, _ = build_client_with_fake(SupabaseRestClient)
    repo = SupabaseTransactionRepository(client)
    with pytest.raises(UnknownTransactionError):
        await repo.stop_transaction(uuid.uuid4(), meter_stop=100, stop_timestamp=datetime.now(timezone.utc), reason=None)


@pytest.mark.asyncio
async def test_meter_value_sink_writes_batch_resolving_charger_uuid():
    client, fake = build_client_with_fake(SupabaseRestClient)
    await SupabaseChargerRegistry(client).upsert_on_boot("charger-1", TENANT_ID, None, None, None)
    charger_uuid = fake.tables["charger"][0]["id"]

    sink = SupabaseMeterValueSink(client)
    txn_id = uuid.uuid4()
    readings = [
        MeterReading(
            tenant_id=TENANT_ID, transaction_id=txn_id, charger_id="charger-1",
            ts=datetime.now(timezone.utc), measurand="Energy.Active.Import.Register", value=1500.0, unit="Wh",
        )
    ]

    await sink.write_batch(readings)

    stored = fake.tables["meter_value"]
    assert len(stored) == 1
    assert stored[0]["charger_id"] == charger_uuid
    assert stored[0]["value"] == 1500.0

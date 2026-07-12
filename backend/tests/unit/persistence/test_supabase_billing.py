import uuid

import pytest

from evagg.billing.tariff_calculator import TariffComponentInput
from evagg.billing.tariffs import TariffNotFoundError
from evagg.persistence.supabase_billing import SupabaseTariffStore, SupabaseWalletLedgerStore
from evagg.persistence.supabase_client import SupabaseRestClient

from .fake_postgrest import build_client_with_fake

TENANT_ID = uuid.uuid4()


@pytest.mark.asyncio
async def test_tariff_create_then_get_round_trips_components():
    client, _ = build_client_with_fake(SupabaseRestClient)
    store = SupabaseTariffStore(client)
    components = [TariffComponentInput(type="energy", price_minor_units=50)]

    created = await store.create(TENANT_ID, "Standard", "USD", components)
    fetched = await store.get(created.id)

    assert fetched is not None
    assert fetched.name == "Standard"
    assert fetched.currency == "USD"
    assert len(fetched.components) == 1
    assert fetched.components[0].type == "energy"
    assert fetched.components[0].price_minor_units == 50


@pytest.mark.asyncio
async def test_tariff_get_missing_returns_none():
    client, _ = build_client_with_fake(SupabaseRestClient)
    store = SupabaseTariffStore(client)
    assert await store.get(uuid.uuid4()) is None


@pytest.mark.asyncio
async def test_tariff_update_replaces_components():
    client, _ = build_client_with_fake(SupabaseRestClient)
    store = SupabaseTariffStore(client)
    created = await store.create(
        TENANT_ID, "Standard", "USD", [TariffComponentInput(type="energy", price_minor_units=50)]
    )

    updated = await store.update(
        created.id, "Peak", [TariffComponentInput(type="energy", price_minor_units=75), TariffComponentInput(type="flat", price_minor_units=1000)]
    )
    fetched = await store.get(created.id)

    assert updated.name == "Peak"
    assert fetched.name == "Peak"
    assert len(fetched.components) == 2
    assert {c.type for c in fetched.components} == {"energy", "flat"}


@pytest.mark.asyncio
async def test_tariff_update_missing_raises():
    client, _ = build_client_with_fake(SupabaseRestClient)
    store = SupabaseTariffStore(client)
    with pytest.raises(TariffNotFoundError):
        await store.update(uuid.uuid4(), "Nope", [])


@pytest.mark.asyncio
async def test_wallet_ledger_append_and_sum():
    client, fake = build_client_with_fake(SupabaseRestClient)
    wallet = fake.seed("wallet", {"tenant_id": str(TENANT_ID), "driver_id": str(uuid.uuid4()), "currency": "USD"})
    wallet_id = uuid.UUID(wallet["id"])
    store = SupabaseWalletLedgerStore(client)

    await store.append(wallet_id, 5000, "topup", "psp-txn-1")
    await store.append(wallet_id, -1200, "charge_deduction", "session-1")

    assert await store.sum_for_wallet(wallet_id) == 3800


@pytest.mark.asyncio
async def test_wallet_ledger_has_reference_dedups_webhook_redelivery():
    client, fake = build_client_with_fake(SupabaseRestClient)
    wallet = fake.seed("wallet", {"tenant_id": str(TENANT_ID), "driver_id": str(uuid.uuid4()), "currency": "USD"})
    wallet_id = uuid.UUID(wallet["id"])
    store = SupabaseWalletLedgerStore(client)

    assert await store.has_reference(wallet_id, "psp-txn-1") is False
    await store.append(wallet_id, 5000, "topup", "psp-txn-1")
    assert await store.has_reference(wallet_id, "psp-txn-1") is True


@pytest.mark.asyncio
async def test_wallet_service_end_to_end_against_supabase_repo():
    """The same WalletService the app actually uses, just backed by the
    Supabase repo instead of InMemoryWalletLedgerStore — proves the repo
    satisfies the real Protocol, not just its own tests."""
    from evagg.billing.payment_provider import StubPaymentProvider
    from evagg.billing.wallet import WalletService

    client, fake = build_client_with_fake(SupabaseRestClient)
    wallet = fake.seed("wallet", {"tenant_id": str(TENANT_ID), "driver_id": str(uuid.uuid4()), "currency": "USD"})
    wallet_id = uuid.UUID(wallet["id"])

    service = WalletService(SupabaseWalletLedgerStore(client), StubPaymentProvider())
    txn_ref = await service.initiate_topup(wallet_id, "tok-1", 5000, "USD")
    await service.handle_topup_webhook(wallet_id, txn_ref, 5000)
    # Redelivered webhook must not double-credit.
    await service.handle_topup_webhook(wallet_id, txn_ref, 5000)

    assert await service.get_balance(wallet_id) == 5000

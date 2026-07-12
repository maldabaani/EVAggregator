from __future__ import annotations

import uuid

import pytest

from evagg.billing.payment_provider import StubPaymentProvider
from evagg.billing.wallet import InMemoryWalletLedgerStore, WalletService

WALLET_ID = uuid.uuid4()


@pytest.mark.asyncio
async def test_topup_balance_updates_only_on_psp_success_webhook():
    ledger = InMemoryWalletLedgerStore()
    provider = StubPaymentProvider()
    service = WalletService(ledger, provider)

    txn_ref = await service.initiate_topup(WALLET_ID, "psp-tok-1", amount_minor_units=5000, currency="AED")

    # Balance must not move on the initial charge request alone.
    assert await service.get_balance(WALLET_ID) == 0

    await service.handle_topup_webhook(WALLET_ID, txn_ref, amount_minor_units=5000)

    assert await service.get_balance(WALLET_ID) == 5000


@pytest.mark.asyncio
async def test_duplicate_webhook_delivery_is_idempotent():
    ledger = InMemoryWalletLedgerStore()
    provider = StubPaymentProvider()
    service = WalletService(ledger, provider)
    txn_ref = await service.initiate_topup(WALLET_ID, "psp-tok-1", amount_minor_units=5000, currency="AED")

    await service.handle_topup_webhook(WALLET_ID, txn_ref, amount_minor_units=5000)
    await service.handle_topup_webhook(WALLET_ID, txn_ref, amount_minor_units=5000)  # redelivered
    await service.handle_topup_webhook(WALLET_ID, txn_ref, amount_minor_units=5000)  # redelivered again

    assert await service.get_balance(WALLET_ID) == 5000  # credited exactly once


@pytest.mark.asyncio
async def test_wallet_balance_is_derived_correctly_from_ledger_sum():
    ledger = InMemoryWalletLedgerStore()
    provider = StubPaymentProvider()
    service = WalletService(ledger, provider)

    await ledger.append(WALLET_ID, 10000, "topup", "ref-1")
    await ledger.append(WALLET_ID, -2500, "charge_deduction", "ref-2")
    await ledger.append(WALLET_ID, 5000, "topup", "ref-3")
    await ledger.append(WALLET_ID, -1000, "charge_deduction", "ref-4")

    balance = await service.get_balance(WALLET_ID)

    assert balance == 10000 - 2500 + 5000 - 1000


@pytest.mark.asyncio
async def test_different_wallets_are_isolated():
    ledger = InMemoryWalletLedgerStore()
    provider = StubPaymentProvider()
    service = WalletService(ledger, provider)
    other_wallet_id = uuid.uuid4()

    await ledger.append(WALLET_ID, 5000, "topup", "ref-1")
    await ledger.append(other_wallet_id, 9999, "topup", "ref-2")

    assert await service.get_balance(WALLET_ID) == 5000
    assert await service.get_balance(other_wallet_id) == 9999

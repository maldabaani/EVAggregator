from __future__ import annotations

import uuid
from dataclasses import fields

import pytest

from evagg.billing.payment_methods import (
    DIRECT_CARD,
    InMemoryPaymentMethodStore,
    PaymentMethod,
    WALLET_BALANCE,
)
from evagg.billing.payment_provider import StubPaymentProvider
from evagg.billing.session_billing import (
    CHARGED,
    PAYMENT_FAILED,
    InMemoryChargerAccessStore,
    InMemoryPaymentFailureTracker,
    InMemoryRetryScheduleStore,
    InMemorySessionPaymentStore,
    SessionBillingService,
)
from evagg.billing.wallet import InMemoryWalletLedgerStore

WALLET_ID = uuid.uuid4()
DRIVER_ID = uuid.uuid4()


def _build_service(suspend_after_n_failures: int = 3):
    payment_methods = InMemoryPaymentMethodStore()
    ledger = InMemoryWalletLedgerStore()
    provider = StubPaymentProvider()
    session_payments = InMemorySessionPaymentStore()
    failure_tracker = InMemoryPaymentFailureTracker()
    charger_access = InMemoryChargerAccessStore()
    retry_store = InMemoryRetryScheduleStore()
    service = SessionBillingService(
        payment_methods, ledger, provider, session_payments, failure_tracker, charger_access, retry_store,
        suspend_after_n_failures=suspend_after_n_failures,
    )
    return service, payment_methods, ledger, provider, session_payments, failure_tracker, charger_access, retry_store


@pytest.mark.asyncio
async def test_direct_pay_charges_card_not_wallet_balance():
    service, payment_methods, ledger, provider, session_payments, *_ = _build_service()
    payment_methods.add(PaymentMethod(id=uuid.uuid4(), wallet_id=WALLET_ID, type=DIRECT_CARD, psp_token="tok-1", is_default=True))

    await service.charge_session("session-1", WALLET_ID, DRIVER_ID, amount_minor_units=2000, currency="AED")

    assert provider.charges == [("tok-1", 2000, "AED", "session:session-1")]
    assert ledger.entries_for(WALLET_ID) == []  # wallet balance untouched
    assert await session_payments.get_status("session-1") == CHARGED


@pytest.mark.asyncio
async def test_wallet_balance_method_deducts_from_ledger_not_card():
    service, payment_methods, ledger, provider, session_payments, *_ = _build_service()
    payment_methods.add(PaymentMethod(id=uuid.uuid4(), wallet_id=WALLET_ID, type=WALLET_BALANCE, psp_token=None, is_default=True))

    await service.charge_session("session-1", WALLET_ID, DRIVER_ID, amount_minor_units=2000, currency="AED")

    assert provider.charges == []  # card never touched
    entries = ledger.entries_for(WALLET_ID)
    assert len(entries) == 1
    assert entries[0]["amount_minor_units"] == -2000
    assert entries[0]["type"] == "charge_deduction"


@pytest.mark.asyncio
async def test_failed_direct_charge_marks_session_payment_failed_and_schedules_retry():
    service, payment_methods, ledger, provider, session_payments, failure_tracker, charger_access, retry_store = _build_service()
    payment_methods.add(PaymentMethod(id=uuid.uuid4(), wallet_id=WALLET_ID, type=DIRECT_CARD, psp_token="declined-tok", is_default=True))
    provider.set_failing("declined-tok", True)

    await service.charge_session("session-1", WALLET_ID, DRIVER_ID, amount_minor_units=2000, currency="AED")

    assert await session_payments.get_status("session-1") == PAYMENT_FAILED
    assert len(retry_store.scheduled) == 1
    assert retry_store.scheduled[0][0] == "session-1"
    assert not await charger_access.is_suspended(DRIVER_ID)  # not yet at the failure threshold


@pytest.mark.asyncio
async def test_repeated_payment_failures_suspends_charger_access():
    service, payment_methods, ledger, provider, session_payments, failure_tracker, charger_access, retry_store = _build_service(
        suspend_after_n_failures=3
    )
    payment_methods.add(PaymentMethod(id=uuid.uuid4(), wallet_id=WALLET_ID, type=DIRECT_CARD, psp_token="declined-tok", is_default=True))
    provider.set_failing("declined-tok", True)

    for i in range(3):
        await service.charge_session(f"session-{i}", WALLET_ID, DRIVER_ID, amount_minor_units=2000, currency="AED")

    assert await charger_access.is_suspended(DRIVER_ID)
    assert len(retry_store.scheduled) == 3


@pytest.mark.asyncio
async def test_successful_charge_after_failures_resets_the_failure_count():
    service, payment_methods, ledger, provider, session_payments, failure_tracker, charger_access, retry_store = _build_service(
        suspend_after_n_failures=3
    )
    payment_methods.add(PaymentMethod(id=uuid.uuid4(), wallet_id=WALLET_ID, type=DIRECT_CARD, psp_token="tok-1", is_default=True))

    provider.set_failing("tok-1", True)
    await service.charge_session("session-1", WALLET_ID, DRIVER_ID, amount_minor_units=2000, currency="AED")
    provider.set_failing("tok-1", False)
    await service.charge_session("session-2", WALLET_ID, DRIVER_ID, amount_minor_units=2000, currency="AED")

    provider.set_failing("tok-1", True)
    await service.charge_session("session-3", WALLET_ID, DRIVER_ID, amount_minor_units=2000, currency="AED")
    await service.charge_session("session-4", WALLET_ID, DRIVER_ID, amount_minor_units=2000, currency="AED")

    # Only 2 consecutive failures since the reset -> not suspended yet.
    assert not await charger_access.is_suspended(DRIVER_ID)


def test_no_raw_card_data_persisted_only_psp_token():
    """PaymentMethod has no field for a PAN/CVV at all — only psp_token —
    so raw card data structurally cannot be persisted through this type."""
    field_names = {f.name for f in fields(PaymentMethod)}

    assert "psp_token" in field_names
    disallowed = {"card_number", "cvv", "pan", "expiry", "cardholder_name"}
    assert field_names.isdisjoint(disallowed)

"""Task 3.3 — charges a session per the driver's selected payment method at
session end, and handles the direct-card failure path: mark the session
`payment_failed` (never silently unbilled), schedule a retry, and suspend
charger access for that driver after N consecutive failures.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Protocol

from evagg.billing.payment_methods import DIRECT_CARD, PaymentMethodStore, WALLET_BALANCE
from evagg.billing.payment_provider import PaymentProvider, PaymentProviderError
from evagg.billing.wallet import CHARGE_DEDUCTION, WalletLedgerStore

PENDING = "pending"
CHARGED = "charged"
PAYMENT_FAILED = "payment_failed"

DEFAULT_SUSPEND_AFTER_N_FAILURES = 3
DEFAULT_RETRY_BACKOFF_MINUTES = (5, 30, 120)


class NoPaymentMethodError(Exception):
    pass


class SessionPaymentStore(Protocol):
    async def mark_status(self, session_id: str, status: str) -> None: ...

    async def get_status(self, session_id: str) -> str | None: ...


class InMemorySessionPaymentStore:
    def __init__(self) -> None:
        self._statuses: dict[str, str] = {}

    async def mark_status(self, session_id: str, status: str) -> None:
        self._statuses[session_id] = status

    async def get_status(self, session_id: str) -> str | None:
        return self._statuses.get(session_id)


class ChargerAccessStore(Protocol):
    async def suspend(self, driver_id: uuid.UUID) -> None: ...

    async def is_suspended(self, driver_id: uuid.UUID) -> bool: ...


class InMemoryChargerAccessStore:
    def __init__(self) -> None:
        self._suspended: set[uuid.UUID] = set()

    async def suspend(self, driver_id: uuid.UUID) -> None:
        self._suspended.add(driver_id)

    async def is_suspended(self, driver_id: uuid.UUID) -> bool:
        return driver_id in self._suspended


class PaymentFailureTracker(Protocol):
    async def record_failure(self, driver_id: uuid.UUID) -> int: ...

    async def reset(self, driver_id: uuid.UUID) -> None: ...


class InMemoryPaymentFailureTracker:
    def __init__(self) -> None:
        self._counts: dict[uuid.UUID, int] = {}

    async def record_failure(self, driver_id: uuid.UUID) -> int:
        self._counts[driver_id] = self._counts.get(driver_id, 0) + 1
        return self._counts[driver_id]

    async def reset(self, driver_id: uuid.UUID) -> None:
        self._counts[driver_id] = 0


class RetryScheduleStore(Protocol):
    async def schedule_retry(self, session_id: str, attempt_number: int, next_attempt_at: datetime) -> None: ...


class InMemoryRetryScheduleStore:
    def __init__(self) -> None:
        self.scheduled: list[tuple[str, int, datetime]] = []

    async def schedule_retry(self, session_id: str, attempt_number: int, next_attempt_at: datetime) -> None:
        self.scheduled.append((session_id, attempt_number, next_attempt_at))


def _backoff_minutes_for_attempt(attempt_number: int) -> int:
    index = min(attempt_number - 1, len(DEFAULT_RETRY_BACKOFF_MINUTES) - 1)
    return DEFAULT_RETRY_BACKOFF_MINUTES[index]


class SessionBillingService:
    def __init__(
        self,
        payment_method_store: PaymentMethodStore,
        wallet_ledger: WalletLedgerStore,
        provider: PaymentProvider,
        session_payment_store: SessionPaymentStore,
        failure_tracker: PaymentFailureTracker,
        charger_access_store: ChargerAccessStore,
        retry_store: RetryScheduleStore,
        suspend_after_n_failures: int = DEFAULT_SUSPEND_AFTER_N_FAILURES,
        clock=lambda: datetime.now(timezone.utc),
    ) -> None:
        self._payment_method_store = payment_method_store
        self._wallet_ledger = wallet_ledger
        self._provider = provider
        self._session_payment_store = session_payment_store
        self._failure_tracker = failure_tracker
        self._charger_access_store = charger_access_store
        self._retry_store = retry_store
        self._suspend_after_n_failures = suspend_after_n_failures
        self._clock = clock

    async def charge_session(
        self,
        session_id: str,
        wallet_id: uuid.UUID,
        driver_id: uuid.UUID,
        amount_minor_units: int,
        currency: str,
    ) -> None:
        method = await self._payment_method_store.get_default(wallet_id)

        if method is None or method.type == WALLET_BALANCE:
            await self._wallet_ledger.append(wallet_id, -amount_minor_units, CHARGE_DEDUCTION, f"session:{session_id}")
            await self._session_payment_store.mark_status(session_id, CHARGED)
            return

        if method.type != DIRECT_CARD or method.psp_token is None:
            raise NoPaymentMethodError(f"wallet {wallet_id} has no usable payment method")

        idempotency_key = f"session:{session_id}"
        try:
            await self._provider.charge(method.psp_token, amount_minor_units, currency, idempotency_key)
        except PaymentProviderError:
            await self._session_payment_store.mark_status(session_id, PAYMENT_FAILED)
            failure_count = await self._failure_tracker.record_failure(driver_id)
            next_attempt_at = self._clock() + timedelta(minutes=_backoff_minutes_for_attempt(failure_count))
            await self._retry_store.schedule_retry(session_id, failure_count, next_attempt_at)
            if failure_count >= self._suspend_after_n_failures:
                await self._charger_access_store.suspend(driver_id)
            return

        await self._session_payment_store.mark_status(session_id, CHARGED)
        await self._failure_tracker.reset(driver_id)

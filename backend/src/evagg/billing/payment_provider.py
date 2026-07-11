"""Task 3.3 — `PaymentProvider`: the PSP abstraction, built first per this
build's own decision, with a stub implementation standing in for a real PSP
(Stripe/Telr/Checkout.com). Swapping in a real PSP later only means writing a
new class satisfying this same interface — wallet/ledger/session-billing
logic never changes.

Card details never reach this interface at all: every method takes a
`psp_token` (already tokenized by the PSP's own hosted fields), never a PAN —
so "don't persist raw card data" isn't a runtime check here, it's structural.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class PaymentProviderError(Exception):
    pass


class PaymentProvider(Protocol):
    async def charge(self, psp_token: str, amount_minor_units: int, currency: str, idempotency_key: str) -> str:
        """Initiates a charge, returning a PSP transaction reference. In
        production this is confirmed asynchronously via webhook — a non-error
        return here means "accepted for processing", not "settled"."""
        ...


@dataclass
class StubPaymentProvider:
    """Stand-in PSP. Records every charge attempt for test assertions;
    `set_failing` lets tests simulate a declined/errored charge without any
    real network call."""

    charges: list[tuple[str, int, str, str]] = field(default_factory=list)
    _next_txn_id: int = 0
    _failing_tokens: set[str] = field(default_factory=set)

    def set_failing(self, psp_token: str, failing: bool = True) -> None:
        if failing:
            self._failing_tokens.add(psp_token)
        else:
            self._failing_tokens.discard(psp_token)

    async def charge(self, psp_token: str, amount_minor_units: int, currency: str, idempotency_key: str) -> str:
        self.charges.append((psp_token, amount_minor_units, currency, idempotency_key))
        if psp_token in self._failing_tokens:
            raise PaymentProviderError(f"card declined for token {psp_token}")
        self._next_txn_id += 1
        return f"stub-txn-{self._next_txn_id}"

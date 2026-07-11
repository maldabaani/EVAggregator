"""Task 3.3 — `PaymentProvider`: the PSP abstraction, built first per this
build's own decision, with a stub implementation standing in for a real PSP
(Stripe/Telr/Checkout.com). Swapping in a real PSP later only means writing a
new class satisfying this same interface — wallet/ledger/session-billing
logic never changes. `StripePaymentProvider` is that real implementation,
following the same retry/backoff shape as `ElectricityMapsClient` (Task 1.4).

Card details never reach this interface at all: every method takes a
`psp_token` (already tokenized by the PSP's own hosted fields), never a PAN —
so "don't persist raw card data" isn't a runtime check here, it's structural.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Protocol

import httpx


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


class StripePaymentProvider:
    """Real PSP adapter against Stripe's Payment Intents API. `psp_token` is
    an already-tokenized Stripe PaymentMethod id (`pm_...`) from the client's
    hosted card fields — this class never sees a PAN.

    Retries are only applied to transport failures and 5xx responses (the
    request may not have reached Stripe, or Stripe couldn't process it) —
    never to a 4xx decline, which is a definitive answer that retrying
    wouldn't change. The idempotency key is forwarded as Stripe's own
    `Idempotency-Key` header, so a retried request (or a caller retrying
    `charge_session` after a crash) is deduplicated by Stripe itself, not just
    by this client.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.stripe.com/v1",
        max_attempts: int = 3,
        backoff_base_seconds: float = 0.5,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._max_attempts = max_attempts
        self._backoff_base_seconds = backoff_base_seconds
        self._http_client = http_client

    async def charge(self, psp_token: str, amount_minor_units: int, currency: str, idempotency_key: str) -> str:
        client = self._http_client or httpx.AsyncClient()
        last_exc: Exception | None = None

        for attempt in range(self._max_attempts):
            try:
                response = await client.post(
                    f"{self._base_url}/payment_intents",
                    data={
                        "amount": amount_minor_units,
                        "currency": currency.lower(),
                        "payment_method": psp_token,
                        "confirm": "true",
                        "off_session": "true",
                    },
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Idempotency-Key": idempotency_key,
                    },
                )
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < self._max_attempts - 1:
                    await asyncio.sleep(self._backoff_base_seconds * (2**attempt))
                continue

            if response.status_code >= 500:
                last_exc = PaymentProviderError(f"PSP server error (status {response.status_code})")
                if attempt < self._max_attempts - 1:
                    await asyncio.sleep(self._backoff_base_seconds * (2**attempt))
                continue

            try:
                data = response.json()
            except ValueError as exc:
                raise PaymentProviderError("malformed PSP response body") from exc

            if response.status_code >= 400:
                error = data.get("error") or {}
                message = error.get("message", f"PSP declined the charge (status {response.status_code})")
                raise PaymentProviderError(message)

            status = data.get("status")
            if status not in {"succeeded", "processing", "requires_capture"}:
                raise PaymentProviderError(f"payment intent ended in unexpected status: {status!r}")

            return data["id"]

        raise PaymentProviderError(
            f"PSP request failed after {self._max_attempts} attempts"
        ) from last_exc

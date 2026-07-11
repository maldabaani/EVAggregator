"""Task 3.3 — the wallet ledger is append-only and is the source of truth;
`balance` is always a derived sum over it, never a value mutated in place
(closes the class of bugs where a cached balance drifts from its history).

Top-up balance only updates on PSP webhook confirmation, not on the initial
charge request — and the webhook handler is idempotent by PSP transaction id,
since a webhook can be (and will be) redelivered.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from evagg.billing.payment_provider import PaymentProvider

TOPUP = "topup"
CHARGE_DEDUCTION = "charge_deduction"
REFUND = "refund"


class WalletLedgerStore(Protocol):
    async def append(self, wallet_id: uuid.UUID, amount_minor_units: int, entry_type: str, reference_id: str) -> None: ...

    async def sum_for_wallet(self, wallet_id: uuid.UUID) -> int: ...

    async def has_reference(self, wallet_id: uuid.UUID, reference_id: str) -> bool: ...


class InMemoryWalletLedgerStore:
    def __init__(self) -> None:
        self._entries: list[dict] = []

    async def append(self, wallet_id: uuid.UUID, amount_minor_units: int, entry_type: str, reference_id: str) -> None:
        self._entries.append(
            {"wallet_id": wallet_id, "amount_minor_units": amount_minor_units, "type": entry_type, "reference_id": reference_id}
        )

    async def sum_for_wallet(self, wallet_id: uuid.UUID) -> int:
        return sum(e["amount_minor_units"] for e in self._entries if e["wallet_id"] == wallet_id)

    async def has_reference(self, wallet_id: uuid.UUID, reference_id: str) -> bool:
        return any(e["wallet_id"] == wallet_id and e["reference_id"] == reference_id for e in self._entries)

    def entries_for(self, wallet_id: uuid.UUID) -> list[dict]:
        return [e for e in self._entries if e["wallet_id"] == wallet_id]


class WalletService:
    def __init__(self, ledger: WalletLedgerStore, provider: PaymentProvider) -> None:
        self._ledger = ledger
        self._provider = provider

    async def initiate_topup(self, wallet_id: uuid.UUID, psp_token: str, amount_minor_units: int, currency: str) -> str:
        """Only initiates the PSP charge — the wallet balance does not move
        until `handle_topup_webhook` confirms success."""
        idempotency_key = f"topup:{wallet_id}:{uuid.uuid4()}"
        return await self._provider.charge(psp_token, amount_minor_units, currency, idempotency_key)

    async def handle_topup_webhook(self, wallet_id: uuid.UUID, psp_transaction_id: str, amount_minor_units: int) -> None:
        if await self._ledger.has_reference(wallet_id, psp_transaction_id):
            return  # already credited — redelivered webhook, not a second top-up
        await self._ledger.append(wallet_id, amount_minor_units, TOPUP, psp_transaction_id)

    async def get_balance(self, wallet_id: uuid.UUID) -> int:
        return await self._ledger.sum_for_wallet(wallet_id)

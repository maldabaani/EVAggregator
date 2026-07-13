"""Task 3.3 — a driver's payment method: `wallet_balance` (deduct from the
wallet ledger at session end) or `direct_card` (charge the card directly for
that session's cost instead). Note there is no field here for a raw card
number/CVV at all — only `psp_token` — so "never persist raw card data" is
enforced by this type's shape, not by a runtime check.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

WALLET_BALANCE = "wallet_balance"
DIRECT_CARD = "direct_card"


@dataclass(frozen=True)
class PaymentMethod:
    id: uuid.UUID
    wallet_id: uuid.UUID
    type: str  # 'wallet_balance' | 'direct_card'
    psp_token: str | None
    is_default: bool


class PaymentMethodStore(Protocol):
    async def get_default(self, wallet_id: uuid.UUID) -> PaymentMethod | None: ...

    async def set_default(self, wallet_id: uuid.UUID, method_type: str, psp_token: str | None) -> PaymentMethod: ...


class InMemoryPaymentMethodStore:
    def __init__(self) -> None:
        self._methods: dict[uuid.UUID, PaymentMethod] = {}

    def add(self, method: PaymentMethod) -> None:
        if method.is_default:
            self._methods[method.wallet_id] = method

    async def get_default(self, wallet_id: uuid.UUID) -> PaymentMethod | None:
        return self._methods.get(wallet_id)

    async def set_default(self, wallet_id: uuid.UUID, method_type: str, psp_token: str | None) -> PaymentMethod:
        method = PaymentMethod(id=uuid.uuid4(), wallet_id=wallet_id, type=method_type, psp_token=psp_token, is_default=True)
        self._methods[wallet_id] = method
        return method

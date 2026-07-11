"""Task 3.2 — promotion codes and seasonal auto-applied promotions.

`value` for a `percent` discount is basis points out of 10000 (1000 = 10.00%)
— integer, never a float percentage — consistent with the standards' "never
float" rule for anything money-adjacent. `value` for a `flat` discount is
integer minor units, same as everywhere else.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class Promotion:
    id: uuid.UUID
    tenant_id: uuid.UUID
    code: str | None  # None => seasonal, auto-applied by date range
    discount_type: str  # 'percent' | 'flat'
    value: int
    valid_from: datetime
    valid_to: datetime
    usage_limit: int | None


class PromotionError(Exception):
    pass


class PromotionStore(Protocol):
    async def get_by_code(self, code: str) -> Promotion | None: ...


class PromotionRedemptionStore(Protocol):
    async def count_redemptions(self, promotion_id: uuid.UUID) -> int: ...

    async def record_redemption(self, promotion_id: uuid.UUID, session_id: str) -> None: ...


class InMemoryPromotionStore:
    def __init__(self, promotions: list[Promotion] | None = None) -> None:
        self._by_code: dict[str, Promotion] = {p.code: p for p in (promotions or []) if p.code is not None}

    def add(self, promotion: Promotion) -> None:
        if promotion.code is not None:
            self._by_code[promotion.code] = promotion

    async def get_by_code(self, code: str) -> Promotion | None:
        return self._by_code.get(code)


class InMemoryPromotionRedemptionStore:
    def __init__(self) -> None:
        self._redemptions: list[tuple[uuid.UUID, str]] = []

    async def count_redemptions(self, promotion_id: uuid.UUID) -> int:
        return sum(1 for pid, _ in self._redemptions if pid == promotion_id)

    async def record_redemption(self, promotion_id: uuid.UUID, session_id: str) -> None:
        self._redemptions.append((promotion_id, session_id))


def is_promo_within_validity_window(promotion: Promotion, now: datetime) -> bool:
    return promotion.valid_from <= now <= promotion.valid_to


async def redeem_promo_code(
    code: str,
    session_id: str,
    now: datetime,
    promotion_store: PromotionStore,
    redemption_store: PromotionRedemptionStore,
) -> Promotion:
    """Validates a promo code (exists, within its validity window, under its
    usage limit) and records the redemption — all in one call so a caller
    can never apply a discount without also counting against the limit."""
    promotion = await promotion_store.get_by_code(code)
    if promotion is None:
        raise PromotionError(f"unknown promo code: {code}")

    if not is_promo_within_validity_window(promotion, now):
        raise PromotionError(f"promo code expired or not yet valid: {code}")

    if promotion.usage_limit is not None:
        current_count = await redemption_store.count_redemptions(promotion.id)
        if current_count >= promotion.usage_limit:
            raise PromotionError(f"promo code usage limit reached: {code}")

    await redemption_store.record_redemption(promotion.id, session_id)
    return promotion


def apply_discount(base_amount_minor_units: int, promotion: Promotion) -> int:
    if promotion.discount_type == "percent":
        discount = round(base_amount_minor_units * promotion.value / 10_000)
    elif promotion.discount_type == "flat":
        discount = promotion.value
    else:
        raise ValueError(f"unknown discount_type: {promotion.discount_type}")
    return max(0, base_amount_minor_units - discount)

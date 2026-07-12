"""Task 3.2 — override resolution order, documented here (not just in a
comment on the model) so it's a single reviewable source of truth:

    1. promotion code (if valid)
    2. site-specific override
    3. operator-level override
    4. tenant default tariff

First match wins. A promo code is a discount applied on top of whichever
tariff resolves from steps 2-4 — but it's checked *first* in this chain
because an active promo must never be shadowed by a site/operator override
existing (see the acceptance criteria: a site override takes precedence over
the tenant default, but never over an active promo code).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from evagg.billing.promotions import Promotion, PromotionStore, is_promo_within_validity_window


@dataclass(frozen=True)
class SiteOverride:
    site_id: uuid.UUID
    tariff_id: uuid.UUID


@dataclass(frozen=True)
class OperatorOverride:
    operator_id: uuid.UUID
    tariff_id: uuid.UUID


class OverrideStore(Protocol):
    async def get_site_override(self, site_id: uuid.UUID) -> SiteOverride | None: ...

    async def get_operator_override(self, operator_id: uuid.UUID) -> OperatorOverride | None: ...


class InMemoryOverrideStore:
    def __init__(self) -> None:
        self._site_overrides: dict[uuid.UUID, SiteOverride] = {}
        self._operator_overrides: dict[uuid.UUID, OperatorOverride] = {}

    def set_site_override(self, site_id: uuid.UUID, tariff_id: uuid.UUID) -> None:
        self._site_overrides[site_id] = SiteOverride(site_id, tariff_id)

    def set_operator_override(self, operator_id: uuid.UUID, tariff_id: uuid.UUID) -> None:
        self._operator_overrides[operator_id] = OperatorOverride(operator_id, tariff_id)

    async def get_site_override(self, site_id: uuid.UUID) -> SiteOverride | None:
        return self._site_overrides.get(site_id)

    async def get_operator_override(self, operator_id: uuid.UUID) -> OperatorOverride | None:
        return self._operator_overrides.get(operator_id)


@dataclass(frozen=True)
class PricingResolution:
    source: str  # 'promo' | 'site' | 'operator' | 'default'
    tariff_id: uuid.UUID | None
    promotion: Promotion | None = None


async def resolve_pricing_source(
    default_tariff_id: uuid.UUID,
    override_store: OverrideStore,
    promotion_store: PromotionStore,
    now: datetime,
    promo_code: str | None = None,
    site_id: uuid.UUID | None = None,
    operator_id: uuid.UUID | None = None,
) -> PricingResolution:
    if promo_code is not None:
        promotion = await promotion_store.get_by_code(promo_code)
        if promotion is not None and is_promo_within_validity_window(promotion, now):
            return PricingResolution(source="promo", tariff_id=None, promotion=promotion)

    if site_id is not None:
        site_override = await override_store.get_site_override(site_id)
        if site_override is not None:
            return PricingResolution(source="site", tariff_id=site_override.tariff_id)

    if operator_id is not None:
        operator_override = await override_store.get_operator_override(operator_id)
        if operator_override is not None:
            return PricingResolution(source="operator", tariff_id=operator_override.tariff_id)

    return PricingResolution(source="default", tariff_id=default_tariff_id)

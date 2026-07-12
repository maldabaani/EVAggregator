from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from evagg.billing.promotions import (
    InMemoryPromotionRedemptionStore,
    InMemoryPromotionStore,
    Promotion,
    PromotionError,
    apply_discount,
    redeem_promo_code,
)

TENANT_ID = uuid.uuid4()
NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _percent_promo(value_bps: int = 1000, usage_limit: int | None = None, code: str = "SUMMER10") -> Promotion:
    return Promotion(
        id=uuid.uuid4(), tenant_id=TENANT_ID, code=code, discount_type="percent", value=value_bps,
        valid_from=NOW - timedelta(days=1), valid_to=NOW + timedelta(days=30), usage_limit=usage_limit,
    )


@pytest.mark.asyncio
async def test_promo_code_applies_correct_discount():
    promotion = _percent_promo(value_bps=1000)  # 10%
    store = InMemoryPromotionStore([promotion])
    redemptions = InMemoryPromotionRedemptionStore()

    redeemed = await redeem_promo_code("SUMMER10", "session-1", NOW, store, redemptions)
    total = apply_discount(base_amount_minor_units=2000, promotion=redeemed)

    assert total == 1800  # 2000 - 10%


@pytest.mark.asyncio
async def test_flat_discount_promo_code_applies_correct_discount():
    promotion = Promotion(
        id=uuid.uuid4(), tenant_id=TENANT_ID, code="FLAT500", discount_type="flat", value=500,
        valid_from=NOW - timedelta(days=1), valid_to=NOW + timedelta(days=1), usage_limit=None,
    )
    store = InMemoryPromotionStore([promotion])
    redemptions = InMemoryPromotionRedemptionStore()

    redeemed = await redeem_promo_code("FLAT500", "session-1", NOW, store, redemptions)
    total = apply_discount(base_amount_minor_units=2000, promotion=redeemed)

    assert total == 1500


@pytest.mark.asyncio
async def test_discount_never_takes_total_below_zero():
    promotion = Promotion(
        id=uuid.uuid4(), tenant_id=TENANT_ID, code="FLAT500", discount_type="flat", value=5000,
        valid_from=NOW - timedelta(days=1), valid_to=NOW + timedelta(days=1), usage_limit=None,
    )

    total = apply_discount(base_amount_minor_units=2000, promotion=promotion)

    assert total == 0


@pytest.mark.asyncio
async def test_promo_code_usage_limit_enforced():
    promotion = _percent_promo(usage_limit=2)
    store = InMemoryPromotionStore([promotion])
    redemptions = InMemoryPromotionRedemptionStore()

    await redeem_promo_code("SUMMER10", "session-1", NOW, store, redemptions)
    await redeem_promo_code("SUMMER10", "session-2", NOW, store, redemptions)

    with pytest.raises(PromotionError):
        await redeem_promo_code("SUMMER10", "session-3", NOW, store, redemptions)


@pytest.mark.asyncio
async def test_promo_code_under_usage_limit_succeeds():
    promotion = _percent_promo(usage_limit=5)
    store = InMemoryPromotionStore([promotion])
    redemptions = InMemoryPromotionRedemptionStore()

    await redeem_promo_code("SUMMER10", "session-1", NOW, store, redemptions)
    result = await redeem_promo_code("SUMMER10", "session-2", NOW, store, redemptions)

    assert result.code == "SUMMER10"


@pytest.mark.asyncio
async def test_expired_promo_code_rejected():
    promotion = Promotion(
        id=uuid.uuid4(), tenant_id=TENANT_ID, code="EXPIRED", discount_type="percent", value=1000,
        valid_from=NOW - timedelta(days=60), valid_to=NOW - timedelta(days=1), usage_limit=None,
    )
    store = InMemoryPromotionStore([promotion])
    redemptions = InMemoryPromotionRedemptionStore()

    with pytest.raises(PromotionError):
        await redeem_promo_code("EXPIRED", "session-1", NOW, store, redemptions)


@pytest.mark.asyncio
async def test_not_yet_valid_promo_code_rejected():
    promotion = Promotion(
        id=uuid.uuid4(), tenant_id=TENANT_ID, code="FUTURE", discount_type="percent", value=1000,
        valid_from=NOW + timedelta(days=1), valid_to=NOW + timedelta(days=30), usage_limit=None,
    )
    store = InMemoryPromotionStore([promotion])
    redemptions = InMemoryPromotionRedemptionStore()

    with pytest.raises(PromotionError):
        await redeem_promo_code("FUTURE", "session-1", NOW, store, redemptions)


@pytest.mark.asyncio
async def test_unknown_promo_code_rejected():
    store = InMemoryPromotionStore()
    redemptions = InMemoryPromotionRedemptionStore()

    with pytest.raises(PromotionError):
        await redeem_promo_code("NOT-REAL", "session-1", NOW, store, redemptions)

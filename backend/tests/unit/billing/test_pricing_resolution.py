from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from evagg.billing.pricing_resolution import InMemoryOverrideStore, resolve_pricing_source
from evagg.billing.promotions import InMemoryPromotionStore, Promotion

TENANT_ID = uuid.uuid4()
NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)
DEFAULT_TARIFF_ID = uuid.uuid4()
SITE_TARIFF_ID = uuid.uuid4()
OPERATOR_TARIFF_ID = uuid.uuid4()
SITE_ID = uuid.uuid4()
OPERATOR_ID = uuid.uuid4()


def _valid_promo(code: str = "SUMMER10") -> Promotion:
    return Promotion(
        id=uuid.uuid4(), tenant_id=TENANT_ID, code=code, discount_type="percent", value=1000,
        valid_from=NOW - timedelta(days=1), valid_to=NOW + timedelta(days=1), usage_limit=None,
    )


@pytest.fixture
def override_store() -> InMemoryOverrideStore:
    store = InMemoryOverrideStore()
    store.set_site_override(SITE_ID, SITE_TARIFF_ID)
    store.set_operator_override(OPERATOR_ID, OPERATOR_TARIFF_ID)
    return store


@pytest.mark.asyncio
async def test_override_precedence_order_promo_beats_site_beats_operator_beats_default(override_store):
    promotion_store = InMemoryPromotionStore([_valid_promo()])

    # All four are available simultaneously -> promo wins.
    result = await resolve_pricing_source(
        DEFAULT_TARIFF_ID, override_store, promotion_store, NOW,
        promo_code="SUMMER10", site_id=SITE_ID, operator_id=OPERATOR_ID,
    )
    assert result.source == "promo"

    # No promo code this time -> site override wins over operator/default.
    result = await resolve_pricing_source(
        DEFAULT_TARIFF_ID, override_store, promotion_store, NOW,
        promo_code=None, site_id=SITE_ID, operator_id=OPERATOR_ID,
    )
    assert result.source == "site"
    assert result.tariff_id == SITE_TARIFF_ID

    # No promo, no site override -> operator override wins over default.
    result = await resolve_pricing_source(
        DEFAULT_TARIFF_ID, override_store, promotion_store, NOW,
        promo_code=None, site_id=None, operator_id=OPERATOR_ID,
    )
    assert result.source == "operator"
    assert result.tariff_id == OPERATOR_TARIFF_ID

    # Nothing else available -> tenant default tariff.
    result = await resolve_pricing_source(
        DEFAULT_TARIFF_ID, override_store, promotion_store, NOW,
        promo_code=None, site_id=None, operator_id=None,
    )
    assert result.source == "default"
    assert result.tariff_id == DEFAULT_TARIFF_ID


@pytest.mark.asyncio
async def test_site_override_takes_precedence_over_default_but_not_promo(override_store):
    promotion_store = InMemoryPromotionStore([_valid_promo()])

    result = await resolve_pricing_source(
        DEFAULT_TARIFF_ID, override_store, promotion_store, NOW,
        promo_code="SUMMER10", site_id=SITE_ID,
    )

    assert result.source == "promo"  # promo still wins even though a site override exists


@pytest.mark.asyncio
async def test_invalid_promo_code_falls_through_to_site_override(override_store):
    promotion_store = InMemoryPromotionStore()  # "SUMMER10" not registered

    result = await resolve_pricing_source(
        DEFAULT_TARIFF_ID, override_store, promotion_store, NOW,
        promo_code="SUMMER10", site_id=SITE_ID,
    )

    assert result.source == "site"


@pytest.mark.asyncio
async def test_expired_promo_code_falls_through_in_resolution(override_store):
    expired_promo = Promotion(
        id=uuid.uuid4(), tenant_id=TENANT_ID, code="EXPIRED", discount_type="percent", value=1000,
        valid_from=NOW - timedelta(days=60), valid_to=NOW - timedelta(days=1), usage_limit=None,
    )
    promotion_store = InMemoryPromotionStore([expired_promo])

    result = await resolve_pricing_source(
        DEFAULT_TARIFF_ID, override_store, promotion_store, NOW,
        promo_code="EXPIRED", site_id=SITE_ID,
    )

    assert result.source == "site"

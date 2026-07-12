from __future__ import annotations

import uuid

import pytest

from evagg.billing.tariff_calculator import TariffComponentInput
from evagg.billing.tariff_validation import TariffValidationError
from evagg.billing.tariffs import InMemoryTariffStore, InMemoryTenantCurrencyProvider, TariffService

TENANT_ID = uuid.uuid4()


def _build_service():
    store = InMemoryTariffStore()
    currency_provider = InMemoryTenantCurrencyProvider()
    currency_provider.set_currency(TENANT_ID, "AED")
    return TariffService(store, currency_provider), store, currency_provider


@pytest.mark.asyncio
async def test_save_blocked_without_energy_or_time_component():
    service, _, _ = _build_service()
    components = [TariffComponentInput(type="flat", price_minor_units=100, step_size=1)]

    with pytest.raises(TariffValidationError):
        await service.create_tariff(TENANT_ID, "Flat-only tariff", components)


@pytest.mark.asyncio
async def test_save_allowed_with_energy_component():
    service, _, _ = _build_service()
    components = [TariffComponentInput(type="energy", price_minor_units=150, step_size=1)]

    tariff = await service.create_tariff(TENANT_ID, "Basic energy tariff", components)

    assert tariff.name == "Basic energy tariff"


@pytest.mark.asyncio
async def test_save_blocked_with_zero_step_size():
    service, _, _ = _build_service()
    components = [TariffComponentInput(type="energy", price_minor_units=150, step_size=0)]

    with pytest.raises(TariffValidationError):
        await service.create_tariff(TENANT_ID, "Bad tariff", components)


@pytest.mark.asyncio
async def test_currency_locked_to_tenants_configured_currency():
    service, _, _ = _build_service()
    components = [TariffComponentInput(type="energy", price_minor_units=150, step_size=1)]

    tariff = await service.create_tariff(TENANT_ID, "AED tariff", components)

    assert tariff.currency == "AED"


@pytest.mark.asyncio
async def test_preview_uses_the_saved_tariffs_components():
    service, _, _ = _build_service()
    components = [
        TariffComponentInput(type="energy", price_minor_units=150, step_size=1),
        TariffComponentInput(type="flat", price_minor_units=200, step_size=1),
    ]
    tariff = await service.create_tariff(TENANT_ID, "Preview tariff", components)

    total = await service.preview(tariff.id, duration_minutes=30, kwh=15)

    assert total == 15 * 150 + 200


@pytest.mark.asyncio
async def test_editing_a_saved_tariff_does_not_change_its_currency():
    service, _, _ = _build_service()
    components = [TariffComponentInput(type="energy", price_minor_units=150, step_size=1)]
    tariff = await service.create_tariff(TENANT_ID, "Original", components)

    updated = await service.update_tariff(
        tariff.id, "Renamed", [TariffComponentInput(type="time", price_minor_units=10, step_size=1)]
    )

    assert updated.currency == "AED"
    assert updated.name == "Renamed"


@pytest.mark.asyncio
async def test_list_all_tariffs_returns_every_created_tariff():
    service, _, _ = _build_service()
    components = [TariffComponentInput(type="energy", price_minor_units=150, step_size=1)]
    first = await service.create_tariff(TENANT_ID, "First", components)
    second = await service.create_tariff(TENANT_ID, "Second", components)

    tariffs = await service.list_all_tariffs()

    assert {t.id for t in tariffs} == {first.id, second.id}


@pytest.mark.asyncio
async def test_get_tariff_returns_none_for_unknown_id():
    service, _, _ = _build_service()

    assert await service.get_tariff(uuid.uuid4()) is None

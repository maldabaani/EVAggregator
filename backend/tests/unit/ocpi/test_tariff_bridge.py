from __future__ import annotations

import uuid

import pytest

from evagg.billing.tariff_calculator import TariffComponentInput
from evagg.billing.tariffs import InMemoryTariffStore, InMemoryTenantCurrencyProvider, TariffService
from evagg.ocpi.tariff_bridge import OcpiTariffCatalog, to_ocpi_tariff

TENANT_ID = uuid.uuid4()


def _build_service() -> TariffService:
    return TariffService(InMemoryTariffStore(), InMemoryTenantCurrencyProvider())


@pytest.mark.asyncio
async def test_to_ocpi_tariff_maps_component_types_and_converts_to_major_units():
    service = _build_service()
    tariff = await service.create_tariff(
        TENANT_ID,
        "Standard",
        [
            TariffComponentInput(type="energy", price_minor_units=35, step_size=1000),
            TariffComponentInput(type="time", price_minor_units=10, step_size=60),
            TariffComponentInput(type="flat", price_minor_units=500),
            TariffComponentInput(type="idle", price_minor_units=200, applies_after_minutes=15),
        ],
    )

    ocpi_tariff = to_ocpi_tariff(tariff, party_id="EVG", country_code="US")

    assert ocpi_tariff.id == str(tariff.id)
    assert ocpi_tariff.party_id == "EVG"
    assert ocpi_tariff.country_code == "US"
    assert len(ocpi_tariff.elements) == 1
    components = {pc.type: pc for pc in ocpi_tariff.elements[0].price_components}
    assert components["ENERGY"].price == 0.35
    assert components["TIME"].price == 0.10
    assert components["FLAT"].price == 5.00
    assert components["PARKING_TIME"].price == 2.00  # 'idle' maps to OCPI's PARKING_TIME


@pytest.mark.asyncio
async def test_catalog_list_all_returns_every_tariff_under_our_party_identity():
    service = _build_service()
    await service.create_tariff(TENANT_ID, "A", [TariffComponentInput(type="energy", price_minor_units=10)])
    await service.create_tariff(TENANT_ID, "B", [TariffComponentInput(type="energy", price_minor_units=20)])
    catalog = OcpiTariffCatalog(service, party_id="EVG", country_code="US")

    tariffs = await catalog.list_all()

    assert len(tariffs) == 2
    assert all(t.party_id == "EVG" and t.country_code == "US" for t in tariffs)


@pytest.mark.asyncio
async def test_catalog_get_returns_none_for_unknown_or_malformed_id():
    service = _build_service()
    catalog = OcpiTariffCatalog(service, party_id="EVG", country_code="US")

    assert await catalog.get(str(uuid.uuid4())) is None
    assert await catalog.get("not-a-uuid") is None


@pytest.mark.asyncio
async def test_catalog_get_finds_the_matching_tariff():
    service = _build_service()
    tariff = await service.create_tariff(TENANT_ID, "A", [TariffComponentInput(type="energy", price_minor_units=10)])
    catalog = OcpiTariffCatalog(service, party_id="EVG", country_code="US")

    found = await catalog.get(str(tariff.id))

    assert found is not None
    assert found.id == str(tariff.id)

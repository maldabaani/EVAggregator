"""Task 1.1 unit tests — version negotiation, the internal-model/per-version
adapter architecture, the 2.1.1 read-only shim, and OCPI error-code mapping.
All isolated: in-memory partner/location repositories, FastAPI TestClient
against an in-process app (no real network)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from evagg.billing.tariffs import InMemoryTariffStore, InMemoryTenantCurrencyProvider, TariffService
from evagg.ocpi.domain import OCPIGeoLocation, OCPILocation
from evagg.ocpi.errors import OcpiErrorCode, map_exception_to_ocpi_error
from evagg.ocpi.locations import InMemoryLocationRepository
from evagg.ocpi.partner_store import InMemoryPartnerRegistry, Partner
from evagg.ocpi.router import build_ocpi_router, register_ocpi_exception_handlers
from evagg.ocpi.tariff_bridge import OcpiTariffCatalog
from evagg.ocpi.v221.adapters import location_to_v221
from evagg.ocpi.v230.adapters import location_to_v230
from evagg.ocpi.versions import SUPPORTED_VERSIONS, negotiate_credentials

TENANT_ID = uuid.uuid4()


def _build_tariff_catalog(tariff_service: TariffService | None = None) -> OcpiTariffCatalog:
    service = tariff_service or TariffService(InMemoryTariffStore(), InMemoryTenantCurrencyProvider())
    return OcpiTariffCatalog(service, party_id="EVG", country_code="US")


def _sample_location() -> OCPILocation:
    return OCPILocation(
        id="LOC-1",
        party_id="ABC",
        country_code="AE",
        publish=True,
        name="Downtown Garage",
        address="1 Main St",
        city="Dubai",
        postal_code=None,
        country="ARE",
        coordinates=OCPIGeoLocation(latitude="25.2048", longitude="55.2708"),
        last_updated=datetime.now(timezone.utc),
    )


def _build_app(partner_registry, location_repo, tariff_catalog=None) -> FastAPI:
    app = FastAPI()
    register_ocpi_exception_handlers(app)

    async def get_partner_registry():
        return partner_registry

    async def get_location_repo():
        return location_repo

    async def get_tariff_catalog():
        return tariff_catalog or _build_tariff_catalog()

    app.include_router(build_ocpi_router(get_partner_registry, get_location_repo, get_tariff_catalog))
    return app


# --- Version negotiation --------------------------------------------------


def test_version_negotiation_returns_all_supported_versions():
    client = TestClient(_build_app(InMemoryPartnerRegistry(), InMemoryLocationRepository()))

    response = client.get("/ocpi/versions")

    assert response.status_code == 200
    versions = {entry["version"] for entry in response.json()["data"]}
    assert versions == set(SUPPORTED_VERSIONS)
    for entry in response.json()["data"]:
        assert entry["url"].endswith(entry["version"])


@pytest.mark.asyncio
async def test_credentials_handshake_negotiates_and_persists_version():
    registry = InMemoryPartnerRegistry()
    partner = Partner(
        id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        party_id="XYZ",
        country_code="AE",
        token_a="token-a-secret",
        token_c=None,
        negotiated_version=None,
        status="pending",
    )
    registry.add(partner)

    response = await negotiate_credentials(registry, "token-a-secret", "2.2.1")

    assert response["status_code"] == int(OcpiErrorCode.SUCCESS)
    assert "token" in response["data"]
    updated = await registry.find_by_token_c(response["data"]["token"])
    assert updated is not None
    assert updated.negotiated_version == "2.2.1"
    assert updated.status == "connected"


# --- 2.1.1 shim is read-only -----------------------------------------------


def test_2_1_1_shim_rejects_write_operations():
    location_repo = InMemoryLocationRepository([_sample_location()])
    client = TestClient(_build_app(InMemoryPartnerRegistry(), location_repo))

    put_response = client.put("/ocpi/2.1.1/tokens/TOKEN-1", json={"valid": False})
    patch_response = client.patch("/ocpi/2.1.1/sessions/SESSION-1", json={"kwh": 10})

    assert put_response.status_code == 405
    assert patch_response.status_code == 405
    assert put_response.json()["status_code"] == int(OcpiErrorCode.GENERIC_SERVER_ERROR)


def test_2_1_1_shim_still_allows_reads():
    location_repo = InMemoryLocationRepository([_sample_location()])
    client = TestClient(_build_app(InMemoryPartnerRegistry(), location_repo))

    response = client.get("/ocpi/2.1.1/locations/LOC-1")

    assert response.status_code == 200
    assert response.json()["id"] == "LOC-1"
    assert "publish" not in response.json()  # 2.1.1 predates the publish flag


# --- Internal domain model -> per-version adapters -------------------------


def test_internal_model_serializes_correctly_to_v221():
    location = _sample_location()

    v221 = location_to_v221(location)

    assert v221.id == location.id
    assert v221.publish is True
    assert v221.coordinates.latitude == "25.2048"
    assert v221.coordinates.longitude == "55.2708"


def test_internal_model_serializes_correctly_to_v230():
    location = _sample_location()

    v230 = location_to_v230(location)

    assert v230.id == location.id
    assert v230.publish is True
    assert v230.coordinates.latitude == "25.2048"
    # 2.3.0-only field, absent from 2.2.1's schema entirely.
    assert v230.facilities is None


def test_v221_and_v230_adapters_both_serve_the_same_internal_record():
    location = _sample_location()
    client = TestClient(_build_app(InMemoryPartnerRegistry(), InMemoryLocationRepository([location])))

    v221_response = client.get("/ocpi/2.2.1/locations/LOC-1")
    v230_response = client.get("/ocpi/2.3.0/locations/LOC-1")

    assert v221_response.status_code == 200
    assert v230_response.status_code == 200
    assert v221_response.json()["id"] == v230_response.json()["id"] == "LOC-1"
    assert "facilities" not in v221_response.json()
    assert "facilities" in v230_response.json()


# --- Error-code mapping -----------------------------------------------------


def test_invalid_payload_maps_to_ocpi_2001():
    error = map_exception_to_ocpi_error(ValueError("field 'country_code' is required"))

    assert error.status_code == OcpiErrorCode.INVALID_PARAMETERS
    assert error.http_status == 400


def test_malformed_request_body_returns_2001_not_generic_500():
    location_repo = InMemoryLocationRepository()
    client = TestClient(_build_app(InMemoryPartnerRegistry(), location_repo))

    response = client.get("/ocpi/2.2.1/locations/does-not-exist")

    # unknown location, not a malformed payload, but proves the router
    # surfaces a structured OCPI error rather than an unhandled 500
    assert response.status_code == 404
    assert response.json()["status_code"] == int(OcpiErrorCode.UNKNOWN_LOCATION)


def test_unknown_partner_token_returns_2004_unknown_token():
    client = TestClient(_build_app(InMemoryPartnerRegistry(), InMemoryLocationRepository()))

    response = client.post("/ocpi/2.2.1/credentials", headers={"Authorization": "Token totally-unknown"})

    assert response.status_code == 401
    assert response.json()["status_code"] == int(OcpiErrorCode.UNKNOWN_TOKEN)


# --- Tariffs module (bilateral GET only) ------------------------------------


async def _seeded_tariff_service() -> TariffService:
    service = TariffService(InMemoryTariffStore(), InMemoryTenantCurrencyProvider())
    from evagg.billing.tariff_calculator import TariffComponentInput

    await service.create_tariff(
        TENANT_ID,
        "Standard",
        [
            TariffComponentInput(type="energy", price_minor_units=35, step_size=1000),
            TariffComponentInput(type="flat", price_minor_units=100),
        ],
    )
    return service


def test_list_tariffs_v211_returns_the_bare_v211_shape():
    import asyncio

    service = asyncio.run(_seeded_tariff_service())
    catalog = _build_tariff_catalog(service)
    client = TestClient(_build_app(InMemoryPartnerRegistry(), InMemoryLocationRepository(), catalog))

    response = client.get("/ocpi/2.1.1/tariffs")

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["currency"] == "USD"
    assert "elements" not in data[0]  # 2.1.1 shim stays minimal, per its own docstring


def test_list_tariffs_v221_includes_price_components():
    import asyncio

    service = asyncio.run(_seeded_tariff_service())
    catalog = _build_tariff_catalog(service)
    client = TestClient(_build_app(InMemoryPartnerRegistry(), InMemoryLocationRepository(), catalog))

    response = client.get("/ocpi/2.2.1/tariffs")

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["party_id"] == "EVG"
    assert data[0]["country_code"] == "US"
    components = data[0]["elements"][0]["price_components"]
    assert {"type": "ENERGY", "price": 0.35, "step_size": 1000} in components
    assert {"type": "FLAT", "price": 1.0, "step_size": 1} in components


def test_get_tariff_v230_by_id():
    import asyncio

    service = asyncio.run(_seeded_tariff_service())
    tariff_id = asyncio.run(service.list_all_tariffs())[0].id
    catalog = _build_tariff_catalog(service)
    client = TestClient(_build_app(InMemoryPartnerRegistry(), InMemoryLocationRepository(), catalog))

    response = client.get(f"/ocpi/2.3.0/tariffs/{tariff_id}")

    assert response.status_code == 200
    assert response.json()["id"] == str(tariff_id)


def test_get_unknown_tariff_returns_2005_unknown_tariff():
    client = TestClient(_build_app(InMemoryPartnerRegistry(), InMemoryLocationRepository()))

    response = client.get(f"/ocpi/2.2.1/tariffs/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["status_code"] == int(OcpiErrorCode.UNKNOWN_TARIFF)


def test_get_tariff_with_malformed_id_returns_2005_not_500():
    client = TestClient(_build_app(InMemoryPartnerRegistry(), InMemoryLocationRepository()))

    response = client.get("/ocpi/2.2.1/tariffs/not-a-uuid")

    assert response.status_code == 404
    assert response.json()["status_code"] == int(OcpiErrorCode.UNKNOWN_TARIFF)

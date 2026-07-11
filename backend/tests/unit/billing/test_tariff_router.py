import uuid

from fastapi import FastAPI
from starlette.testclient import TestClient

from evagg.billing.tariff_router import build_tariff_router
from evagg.billing.tariffs import InMemoryTariffStore, InMemoryTenantCurrencyProvider, TariffService

TENANT_ID = uuid.uuid4()


def _build_app():
    store = InMemoryTariffStore()
    currency_provider = InMemoryTenantCurrencyProvider()
    currency_provider.set_currency(TENANT_ID, "AED")
    service = TariffService(store, currency_provider)

    async def get_service():
        return service

    app = FastAPI()
    app.include_router(build_tariff_router(get_service))
    return app, service


def test_create_tariff_endpoint_returns_created_tariff():
    app, _ = _build_app()
    client = TestClient(app)

    response = client.post(
        "/admin/tariffs",
        json={
            "tenant_id": str(TENANT_ID),
            "name": "Standard",
            "components": [{"type": "energy", "price_minor_units": 150, "step_size": 1}],
        },
    )

    assert response.status_code == 200
    assert response.json()["currency"] == "AED"


def test_create_tariff_endpoint_returns_422_without_energy_or_time_component():
    app, _ = _build_app()
    client = TestClient(app)

    response = client.post(
        "/admin/tariffs",
        json={
            "tenant_id": str(TENANT_ID),
            "name": "Flat only",
            "components": [{"type": "flat", "price_minor_units": 200, "step_size": 1}],
        },
    )

    assert response.status_code == 422


def test_preview_endpoint_calculates_correct_total_for_sample_session():
    app, _ = _build_app()
    client = TestClient(app)
    create_response = client.post(
        "/admin/tariffs",
        json={
            "tenant_id": str(TENANT_ID),
            "name": "Standard",
            "components": [{"type": "energy", "price_minor_units": 150, "step_size": 1}],
        },
    )
    tariff_id = create_response.json()["id"]

    response = client.get(f"/admin/tariffs/{tariff_id}/preview", params={"duration_min": 30, "kwh": 15})

    assert response.status_code == 200
    assert response.json()["total_minor_units"] == 2250


def test_preview_endpoint_returns_404_for_unknown_tariff():
    app, _ = _build_app()
    client = TestClient(app)

    response = client.get(f"/admin/tariffs/{uuid.uuid4()}/preview", params={"duration_min": 30, "kwh": 15})

    assert response.status_code == 404

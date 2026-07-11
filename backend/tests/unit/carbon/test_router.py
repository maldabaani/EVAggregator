from fastapi import FastAPI
from starlette.testclient import TestClient

from evagg.carbon.cache import InMemoryCarbonCache
from evagg.carbon.router import build_carbon_router
from evagg.carbon.service import CarbonIntensityService
from evagg.carbon.zone_map import InMemoryCarbonZoneMap


class _FakeProvider:
    async def fetch_intensity(self, provider_zone_id: str) -> float:
        return 199.0


def _build_app() -> FastAPI:
    zone_map = InMemoryCarbonZoneMap({("AE", "DXB"): "AE-DXB"})
    service = CarbonIntensityService(zone_map, _FakeProvider(), InMemoryCarbonCache())

    async def get_service():
        return service

    app = FastAPI()
    app.include_router(build_carbon_router(get_service))
    return app


def test_carbon_intensity_endpoint_returns_value_for_mapped_zone():
    client = TestClient(_build_app())

    response = client.get("/internal/carbon-intensity", params={"zone": "AE:DXB"})

    assert response.status_code == 200
    body = response.json()
    assert body["value"] == 199.0
    assert body["stale"] is False


def test_unmapped_zone_returns_404_not_provider_error():
    client = TestClient(_build_app())

    response = client.get("/internal/carbon-intensity", params={"zone": "US:CA"})

    assert response.status_code == 404
    assert "not supported" in response.json()["detail"]


def test_malformed_zone_param_returns_400():
    client = TestClient(_build_app())

    response = client.get("/internal/carbon-intensity", params={"zone": "not-a-valid-zone-format"})

    assert response.status_code == 400

from datetime import datetime, timezone

from fastapi import FastAPI
from starlette.testclient import TestClient

from evagg.driver_app.map_router import build_map_router
from evagg.ocpi.domain import OCPIGeoLocation, OCPILocation
from evagg.ocpi.locations import InMemoryLocationRepository


def _location(loc_id: str, lat: str, lng: str, publish: bool = True, evse_status: str | None = "AVAILABLE") -> OCPILocation:
    return OCPILocation(
        id=loc_id,
        party_id="ABC",
        country_code="AE",
        publish=publish,
        name=f"Station {loc_id}",
        address="1 Main St",
        city="Dubai",
        country="ARE",
        coordinates=OCPIGeoLocation(latitude=lat, longitude=lng),
        last_updated=datetime.now(timezone.utc),
        evse_status=evse_status,
    )


def _build_app(repo: InMemoryLocationRepository) -> FastAPI:
    async def get_repo():
        return repo

    app = FastAPI()
    app.include_router(build_map_router(get_repo))
    return app


def test_returns_only_locations_within_the_bounding_box():
    repo = InMemoryLocationRepository()
    repo.add(_location("in-bounds", "25.20", "55.27"))
    repo.add(_location("out-of-bounds", "40.71", "-74.00"))
    client = TestClient(_build_app(repo))

    response = client.get("/map/chargers", params={"bbox": "25.05,55.10,25.35,55.45"})

    assert response.status_code == 200
    ids = [pin["id"] for pin in response.json()["data"]]
    assert ids == ["in-bounds"]


def test_excludes_unpublished_locations():
    repo = InMemoryLocationRepository()
    repo.add(_location("published", "25.20", "55.27", publish=True))
    repo.add(_location("unpublished", "25.21", "55.28", publish=False))
    client = TestClient(_build_app(repo))

    response = client.get("/map/chargers", params={"bbox": "25.05,55.10,25.35,55.45"})

    ids = [pin["id"] for pin in response.json()["data"]]
    assert ids == ["published"]


def test_available_only_filters_out_non_available_locations():
    repo = InMemoryLocationRepository()
    repo.add(_location("free", "25.20", "55.27", evse_status="AVAILABLE"))
    repo.add(_location("occupied", "25.21", "55.28", evse_status="OCCUPIED"))
    client = TestClient(_build_app(repo))

    response = client.get("/map/chargers", params={"bbox": "25.05,55.10,25.35,55.45", "available_only": "true"})

    ids = [pin["id"] for pin in response.json()["data"]]
    assert ids == ["free"]


def test_returns_empty_data_when_no_locations_match():
    repo = InMemoryLocationRepository()
    client = TestClient(_build_app(repo))

    response = client.get("/map/chargers", params={"bbox": "25.05,55.10,25.35,55.45"})

    assert response.json() == {"data": []}

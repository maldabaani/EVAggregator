import uuid

from fastapi import FastAPI
from starlette.testclient import TestClient

from evagg.driver_app.vehicle_router import build_vehicle_router
from evagg.driver_app.vehicles import InMemoryVehicleStore
from evagg.gateway.jwt_tokens import create_access_token

TENANT_ID = uuid.uuid4()


def _build_app():
    store = InMemoryVehicleStore()

    async def get_store():
        return store

    app = FastAPI()
    app.include_router(build_vehicle_router(get_store))
    return app, store


def _auth_header(driver_id: uuid.UUID) -> dict:
    token = create_access_token(str(driver_id), TENANT_ID)
    return {"Authorization": f"Bearer {token}"}


def test_creating_a_vehicle_requires_a_bearer_token():
    app, _ = _build_app()
    client = TestClient(app)

    response = client.post(
        "/driver/vehicles",
        json={"make": "Tesla", "model": "Model 3", "connector_type": "CCS2", "battery_capacity_kwh": 75.0},
    )

    assert response.status_code == 401


def test_creating_and_listing_a_vehicle_for_the_authenticated_driver():
    app, _ = _build_app()
    client = TestClient(app)
    driver_id = uuid.uuid4()

    create_response = client.post(
        "/driver/vehicles",
        json={"make": "Tesla", "model": "Model 3", "connector_type": "CCS2", "battery_capacity_kwh": 75.0},
        headers=_auth_header(driver_id),
    )
    assert create_response.status_code == 200

    list_response = client.get("/driver/vehicles", headers=_auth_header(driver_id))

    assert list_response.status_code == 200
    data = list_response.json()["data"]
    assert len(data) == 1
    assert data[0]["make"] == "Tesla"
    assert data[0]["plug_and_charge_enabled"] is False


def test_a_driver_cannot_see_another_drivers_vehicles():
    app, _ = _build_app()
    client = TestClient(app)
    driver_a = uuid.uuid4()
    driver_b = uuid.uuid4()
    client.post(
        "/driver/vehicles",
        json={"make": "Tesla", "model": "Model 3", "connector_type": "CCS2", "battery_capacity_kwh": 75.0},
        headers=_auth_header(driver_a),
    )

    response = client.get("/driver/vehicles", headers=_auth_header(driver_b))

    assert response.json()["data"] == []


def test_a_driver_cannot_toggle_plug_and_charge_on_another_drivers_vehicle():
    app, _ = _build_app()
    client = TestClient(app)
    driver_a = uuid.uuid4()
    driver_b = uuid.uuid4()
    created = client.post(
        "/driver/vehicles",
        json={"make": "Tesla", "model": "Model 3", "connector_type": "CCS2", "battery_capacity_kwh": 75.0},
        headers=_auth_header(driver_a),
    ).json()

    response = client.patch(
        f"/driver/vehicles/{created['id']}/plug-and-charge",
        json={"enabled": True},
        headers=_auth_header(driver_b),
    )

    assert response.status_code == 404


def test_toggling_plug_and_charge_on_own_vehicle_succeeds():
    app, _ = _build_app()
    client = TestClient(app)
    driver_id = uuid.uuid4()
    created = client.post(
        "/driver/vehicles",
        json={"make": "Tesla", "model": "Model 3", "connector_type": "CCS2", "battery_capacity_kwh": 75.0},
        headers=_auth_header(driver_id),
    ).json()

    response = client.patch(
        f"/driver/vehicles/{created['id']}/plug-and-charge",
        json={"enabled": True},
        headers=_auth_header(driver_id),
    )

    assert response.status_code == 200
    assert response.json()["plug_and_charge_enabled"] is True


def test_deleting_own_vehicle_removes_it_from_the_list():
    app, _ = _build_app()
    client = TestClient(app)
    driver_id = uuid.uuid4()
    created = client.post(
        "/driver/vehicles",
        json={"make": "Tesla", "model": "Model 3", "connector_type": "CCS2", "battery_capacity_kwh": 75.0},
        headers=_auth_header(driver_id),
    ).json()

    delete_response = client.delete(f"/driver/vehicles/{created['id']}", headers=_auth_header(driver_id))
    list_response = client.get("/driver/vehicles", headers=_auth_header(driver_id))

    assert delete_response.status_code == 204
    assert list_response.json()["data"] == []


def test_deleting_another_drivers_vehicle_returns_404():
    app, _ = _build_app()
    client = TestClient(app)
    driver_a = uuid.uuid4()
    driver_b = uuid.uuid4()
    created = client.post(
        "/driver/vehicles",
        json={"make": "Tesla", "model": "Model 3", "connector_type": "CCS2", "battery_capacity_kwh": 75.0},
        headers=_auth_header(driver_a),
    ).json()

    response = client.delete(f"/driver/vehicles/{created['id']}", headers=_auth_header(driver_b))

    assert response.status_code == 404


def test_malformed_bearer_token_is_rejected():
    app, _ = _build_app()
    client = TestClient(app)

    response = client.get("/driver/vehicles", headers={"Authorization": "Bearer not-a-real-token"})

    assert response.status_code == 401

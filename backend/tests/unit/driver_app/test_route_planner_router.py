import uuid

from fastapi import FastAPI
from starlette.testclient import TestClient

from evagg.driver_app.route_planner import RoutePlan, SuggestedCharger
from evagg.driver_app.route_planner_router import build_route_planner_router
from evagg.driver_app.routing_client import RoutingError
from evagg.driver_app.vehicles import VehicleNotFoundError
from evagg.gateway.jwt_tokens import create_access_token

TENANT_ID = uuid.uuid4()
DRIVER_ID = uuid.uuid4()
VEHICLE_ID = uuid.uuid4()

ORIGIN = {"lat": 25.2048, "lng": 55.2708}
DESTINATION = {"lat": 24.4539, "lng": 54.3773}


class _FakeService:
    def __init__(self, plan=None, error=None):
        self.plan = plan
        self.error = error
        self.last_call = None

    async def plan_route(self, driver_id, vehicle_id, origin, destination):
        self.last_call = (driver_id, vehicle_id, origin, destination)
        if self.error:
            raise self.error
        return self.plan


def _build_app(service):
    async def get_service():
        return service

    app = FastAPI()
    app.include_router(build_route_planner_router(get_service))
    return app


def _auth_header():
    return {"Authorization": f"Bearer {create_access_token(str(DRIVER_ID), TENANT_ID)}"}


def _body():
    return {"vehicle_id": str(VEHICLE_ID), "origin": ORIGIN, "destination": DESTINATION}


def test_planning_a_route_requires_a_bearer_token():
    app = _build_app(_FakeService())
    client = TestClient(app)

    response = client.post("/driver/route-plan", json=_body())

    assert response.status_code == 401


def test_a_successful_plan_returns_its_shape():
    plan = RoutePlan(
        distance_km=132.0,
        duration_minutes=90.0,
        charging_stop_needed=True,
        suggested_charger=SuggestedCharger(id="CP-1", name="Station 1", lat=24.4, lng=54.3),
    )
    app = _build_app(_FakeService(plan=plan))
    client = TestClient(app)

    response = client.post("/driver/route-plan", json=_body(), headers=_auth_header())

    assert response.status_code == 200
    body = response.json()
    assert body["distance_km"] == 132.0
    assert body["charging_stop_needed"] is True
    assert body["suggested_charger"]["id"] == "CP-1"


def test_a_plan_with_no_charging_stop_has_a_null_suggested_charger():
    plan = RoutePlan(distance_km=10.0, duration_minutes=8.0, charging_stop_needed=False, suggested_charger=None)
    app = _build_app(_FakeService(plan=plan))
    client = TestClient(app)

    response = client.post("/driver/route-plan", json=_body(), headers=_auth_header())

    assert response.json()["suggested_charger"] is None


def test_the_authenticated_drivers_id_is_passed_to_the_service():
    plan = RoutePlan(distance_km=1.0, duration_minutes=1.0, charging_stop_needed=False, suggested_charger=None)
    service = _FakeService(plan=plan)
    app = _build_app(service)
    client = TestClient(app)

    client.post("/driver/route-plan", json=_body(), headers=_auth_header())

    assert service.last_call[0] == DRIVER_ID
    assert service.last_call[1] == VEHICLE_ID


def test_an_unknown_vehicle_returns_404():
    app = _build_app(_FakeService(error=VehicleNotFoundError(str(VEHICLE_ID))))
    client = TestClient(app)

    response = client.post("/driver/route-plan", json=_body(), headers=_auth_header())

    assert response.status_code == 404


def test_a_routing_provider_failure_returns_502():
    app = _build_app(_FakeService(error=RoutingError("boom")))
    client = TestClient(app)

    response = client.post("/driver/route-plan", json=_body(), headers=_auth_header())

    assert response.status_code == 502

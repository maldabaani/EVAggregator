import uuid
from datetime import date

from fastapi import FastAPI
from starlette.testclient import TestClient

from evagg.driver_app.usage_insights import DailyUsagePoint
from evagg.driver_app.usage_insights_router import build_usage_insights_router
from evagg.gateway.jwt_tokens import create_access_token

TENANT_ID = uuid.uuid4()
DRIVER_ID = uuid.uuid4()


class _FakeService:
    def __init__(self, points=None):
        self.points = points or []
        self.last_call = None

    async def get_daily_usage(self, driver_id, date_from, date_to):
        self.last_call = (driver_id, date_from, date_to)
        return self.points


def _build_app(service):
    async def get_service():
        return service

    app = FastAPI()
    app.include_router(build_usage_insights_router(get_service))
    return app


def _auth_header():
    return {"Authorization": f"Bearer {create_access_token(str(DRIVER_ID), TENANT_ID)}"}


def test_get_daily_usage_requires_a_bearer_token():
    client = TestClient(_build_app(_FakeService()))

    response = client.get(
        "/driver/usage-insights", params={"date_from": "2026-01-01", "date_to": "2026-01-31"}
    )

    assert response.status_code == 401


def test_get_daily_usage_returns_the_point_shape():
    point = DailyUsagePoint(
        usage_date=date(2026, 1, 10), session_count=2, kwh_total=8.0,
        cost_total_minor_units=800, top_site_name="Downtown Mall",
    )
    service = _FakeService(points=[point])
    client = TestClient(_build_app(service))

    response = client.get(
        "/driver/usage-insights",
        params={"date_from": "2026-01-01", "date_to": "2026-01-31"},
        headers=_auth_header(),
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body == [
        {
            "usage_date": "2026-01-10",
            "session_count": 2,
            "kwh_total": 8.0,
            "cost_total_minor_units": 800,
            "top_site_name": "Downtown Mall",
        }
    ]
    assert service.last_call == (DRIVER_ID, date(2026, 1, 1), date(2026, 1, 31))


def test_get_daily_usage_is_scoped_to_the_authenticated_driver():
    service = _FakeService()
    client = TestClient(_build_app(service))

    client.get(
        "/driver/usage-insights",
        params={"date_from": "2026-01-01", "date_to": "2026-01-31"},
        headers=_auth_header(),
    )

    assert service.last_call[0] == DRIVER_ID

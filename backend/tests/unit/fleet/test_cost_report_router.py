import asyncio
import uuid
from datetime import date, datetime, timezone

from fastapi import FastAPI
from starlette.testclient import TestClient

from evagg.fleet.cost_report import CostReportService
from evagg.fleet.cost_report_router import build_cost_report_router
from evagg.fleet.rollup import InMemoryRollupStore, SessionUsageRecord, run_daily_rollup

TEAM_ID = uuid.uuid4()
DRIVER_A = uuid.uuid4()
DRIVER_B = uuid.uuid4()
SITE_1 = uuid.uuid4()
DAY_1 = date(2026, 6, 1)


def _build_app():
    store = InMemoryRollupStore()
    service = CostReportService(store)

    async def get_service():
        return service

    app = FastAPI()
    app.include_router(build_cost_report_router(get_service))
    return app, store


def _seed(store: InMemoryRollupStore) -> None:
    sessions = [
        SessionUsageRecord(TEAM_ID, DRIVER_A, SITE_1, datetime(2026, 6, 1, 9, tzinfo=timezone.utc), kwh=10, cost_minor_units=1500),
        SessionUsageRecord(TEAM_ID, DRIVER_B, SITE_1, datetime(2026, 6, 1, 12, tzinfo=timezone.utc), kwh=20, cost_minor_units=3000),
    ]
    asyncio.run(run_daily_rollup(store, sessions, DAY_1))


def test_get_cost_report_returns_rows_grouped_by_driver():
    app, store = _build_app()
    _seed(store)
    client = TestClient(app)

    response = client.get(
        f"/admin/teams/{TEAM_ID}/cost-report",
        params={"date_from": "2026-06-01", "date_to": "2026-06-01", "group_by": "driver"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["group_by"] == "driver"
    assert body["total_session_count"] == 2
    assert body["total_kwh"] == 30
    assert body["total_cost_minor_units"] == 4500
    assert {row["key"] for row in body["rows"]} == {str(DRIVER_A), str(DRIVER_B)}


def test_get_cost_report_group_by_site():
    app, store = _build_app()
    _seed(store)
    client = TestClient(app)

    response = client.get(
        f"/admin/teams/{TEAM_ID}/cost-report",
        params={"date_from": "2026-06-01", "date_to": "2026-06-01", "group_by": "site"},
    )

    body = response.json()
    assert body["rows"] == [
        {"key": str(SITE_1), "session_count": 2, "kwh_total": 30, "cost_total_minor_units": 4500}
    ]


def test_get_cost_report_rejects_invalid_group_by():
    app, _ = _build_app()
    client = TestClient(app)

    response = client.get(
        f"/admin/teams/{TEAM_ID}/cost-report",
        params={"date_from": "2026-06-01", "date_to": "2026-06-01", "group_by": "not-a-real-option"},
    )

    assert response.status_code == 422


def test_get_cost_report_csv_returns_matching_totals():
    app, store = _build_app()
    _seed(store)
    client = TestClient(app)

    response = client.get(
        f"/admin/teams/{TEAM_ID}/cost-report/csv",
        params={"date_from": "2026-06-01", "date_to": "2026-06-01", "group_by": "driver"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert f"cost-report-{TEAM_ID}.csv" in response.headers["content-disposition"]
    body_text = response.text
    assert "driver,session_count,kwh_total,cost_total_minor_units" in body_text
    assert str(DRIVER_A) in body_text
    assert str(DRIVER_B) in body_text


def test_get_cost_report_surfaces_incomplete_dates():
    app, store = _build_app()
    asyncio.run(run_daily_rollup(store, [], DAY_1, failing_dates={DAY_1}))
    client = TestClient(app)

    response = client.get(
        f"/admin/teams/{TEAM_ID}/cost-report",
        params={"date_from": "2026-06-01", "date_to": "2026-06-01"},
    )

    assert response.json()["incomplete_dates"] == ["2026-06-01"]

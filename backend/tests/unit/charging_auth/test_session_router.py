"""HTTP-layer tests for build_session_router (status/stop) — business
logic (ownership checks, remote-stop dispatch) is covered by
test_session_start.py."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import FastAPI
from starlette.testclient import TestClient

from evagg.charging_auth.session_start import (
    LiveSessionStatus,
    SessionNotFoundError,
    SessionStartError,
    SessionStatus,
)
from evagg.charging_auth.session_start_router import build_session_router
from evagg.core.tenancy import TenantContextMiddleware

TENANT_ID = uuid.uuid4()
DRIVER_ID = uuid.uuid4()


class _FakeService:
    def __init__(
        self,
        status: SessionStatus | None = None,
        live_status: LiveSessionStatus | None = None,
        error: Exception | None = None,
    ) -> None:
        self.status = status
        self.live_status = live_status
        self.error = error
        self.last_status_call: tuple | None = None
        self.last_live_status_call: tuple | None = None
        self.last_stop_call: tuple | None = None

    async def get_session_status(self, session_id, driver_id):
        self.last_status_call = (session_id, driver_id)
        if self.error:
            raise self.error
        return self.status

    async def get_live_status(self, session_id, driver_id, tenant_id):
        self.last_live_status_call = (session_id, driver_id, tenant_id)
        if self.error:
            raise self.error
        return self.live_status

    async def stop_session(self, session_id, driver_id, tenant_id):
        self.last_stop_call = (session_id, driver_id, tenant_id)
        if self.error:
            raise self.error


def _build_app(service) -> FastAPI:
    async def get_service():
        return service

    app = FastAPI()
    app.include_router(build_session_router(get_service))
    app.add_middleware(TenantContextMiddleware)
    return app


def test_get_status_returns_the_session_shape():
    service = _FakeService(status=SessionStatus(charger_id="CP-001", connector_id=1, active=True))
    client = TestClient(_build_app(service))

    response = client.get(
        "/charging/session/session-1/status",
        params={"driver_id": str(DRIVER_ID)},
        headers={"X-Tenant-Id": str(TENANT_ID)},
    )

    assert response.status_code == 200
    assert response.json() == {"charger_id": "CP-001", "connector_id": 1, "active": True}
    assert service.last_status_call == ("session-1", DRIVER_ID)


def test_get_status_for_an_unowned_or_unknown_session_returns_404():
    service = _FakeService(error=SessionNotFoundError("session-1"))
    client = TestClient(_build_app(service))

    response = client.get(
        "/charging/session/session-1/status",
        params={"driver_id": str(DRIVER_ID)},
        headers={"X-Tenant-Id": str(TENANT_ID)},
    )

    assert response.status_code == 404


def test_get_status_requires_the_tenant_header_too():
    service = _FakeService(status=SessionStatus(charger_id="CP-001", connector_id=1, active=True))
    client = TestClient(_build_app(service))

    response = client.get("/charging/session/session-1/status", params={"driver_id": str(DRIVER_ID)})

    assert response.status_code == 401


def test_get_live_status_returns_the_live_shape():
    started_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    updated_at = datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc)
    service = _FakeService(
        live_status=LiveSessionStatus(
            status="charging", energy_kwh=4.2, power_kw=7.5, cost_minor_units=420,
            currency="AED", started_at=started_at, updated_at=updated_at,
        )
    )
    client = TestClient(_build_app(service))

    response = client.get(
        "/charging/session/session-1/live",
        params={"driver_id": str(DRIVER_ID)},
        headers={"X-Tenant-Id": str(TENANT_ID)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "charging"
    assert body["energy_kwh"] == 4.2
    assert body["power_kw"] == 7.5
    assert body["cost_minor_units"] == 420
    assert body["currency"] == "AED"
    assert service.last_live_status_call == ("session-1", DRIVER_ID, TENANT_ID)


def test_get_live_status_requires_the_tenant_header():
    service = _FakeService()
    client = TestClient(_build_app(service))

    response = client.get("/charging/session/session-1/live", params={"driver_id": str(DRIVER_ID)})

    assert response.status_code == 401


def test_get_live_status_for_an_unowned_or_unknown_session_returns_404():
    service = _FakeService(error=SessionNotFoundError("session-1"))
    client = TestClient(_build_app(service))

    response = client.get(
        "/charging/session/session-1/live",
        params={"driver_id": str(DRIVER_ID)},
        headers={"X-Tenant-Id": str(TENANT_ID)},
    )

    assert response.status_code == 404


def test_stop_requires_the_tenant_header():
    service = _FakeService()
    client = TestClient(_build_app(service))

    response = client.post("/charging/session/session-1/stop", json={"driver_id": str(DRIVER_ID)})

    assert response.status_code == 401
    assert service.last_stop_call is None


def test_a_successful_stop_returns_stopped_true():
    service = _FakeService()
    client = TestClient(_build_app(service))

    response = client.post(
        "/charging/session/session-1/stop",
        json={"driver_id": str(DRIVER_ID)},
        headers={"X-Tenant-Id": str(TENANT_ID)},
    )

    assert response.status_code == 200
    assert response.json() == {"session_id": "session-1", "stopped": True}
    assert service.last_stop_call == ("session-1", DRIVER_ID, TENANT_ID)


def test_stop_for_an_unowned_or_unknown_session_returns_404():
    service = _FakeService(error=SessionNotFoundError("session-1"))
    client = TestClient(_build_app(service))

    response = client.post(
        "/charging/session/session-1/stop",
        json={"driver_id": str(DRIVER_ID)},
        headers={"X-Tenant-Id": str(TENANT_ID)},
    )

    assert response.status_code == 404


def test_stop_with_no_active_transaction_returns_400():
    service = _FakeService(error=SessionStartError("no active transaction on this charger"))
    client = TestClient(_build_app(service))

    response = client.post(
        "/charging/session/session-1/stop",
        json={"driver_id": str(DRIVER_ID)},
        headers={"X-Tenant-Id": str(TENANT_ID)},
    )

    assert response.status_code == 400

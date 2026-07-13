"""HTTP-layer tests for session_start_router.py — the service's own
business logic (payment resolution, remote-command dispatch, error
mapping) is covered by test_session_start.py; this only proves the router
wires the tenant dependency and request/response shapes correctly."""

from __future__ import annotations

import uuid

from fastapi import FastAPI
from starlette.testclient import TestClient

from evagg.charging_auth.session_start import SessionStartError, SessionStartResult
from evagg.charging_auth.session_start_router import build_session_start_router
from evagg.core.tenancy import TenantContextMiddleware

TENANT_ID = uuid.uuid4()
DRIVER_ID = uuid.uuid4()


class _FakeService:
    def __init__(self, result: SessionStartResult | None = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.last_call: tuple | None = None

    async def start_via_app(self, charger_id, connector_id, driver_id, tenant_id):
        self.last_call = ("app", charger_id, connector_id, driver_id, tenant_id)
        if self.error:
            raise self.error
        return self.result

    async def start_via_qr(self, token, driver_id, secret, tenant_id, now=None):
        self.last_call = ("qr", token, driver_id, secret, tenant_id)
        if self.error:
            raise self.error
        return self.result


def _build_app(service) -> FastAPI:
    async def get_service():
        return service

    async def get_mac_store():
        return None

    async def get_validator():
        return None

    app = FastAPI()
    app.include_router(build_session_start_router(get_service, get_mac_store, get_validator))
    app.add_middleware(TenantContextMiddleware)
    return app


def _result() -> SessionStartResult:
    return SessionStartResult(
        session_id="session-1", driver_id=DRIVER_ID, charger_id="CP-001", connector_id=1,
        id_tag="DRIVER:abc", payment_method=None, auth_method="app",
    )


def test_missing_tenant_header_is_rejected_before_reaching_the_service():
    service = _FakeService(result=_result())
    client = TestClient(_build_app(service))

    response = client.post(
        "/charging/session/start/app",
        json={"charger_id": "CP-001", "connector_id": 1, "driver_id": str(DRIVER_ID)},
    )

    assert response.status_code == 401
    assert service.last_call is None


def test_a_successful_app_start_returns_the_session_shape():
    service = _FakeService(result=_result())
    client = TestClient(_build_app(service))

    response = client.post(
        "/charging/session/start/app",
        json={"charger_id": "CP-001", "connector_id": 1, "driver_id": str(DRIVER_ID)},
        headers={"X-Tenant-Id": str(TENANT_ID)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "session-1"
    assert body["charger_id"] == "CP-001"
    assert body["auth_method"] == "app"
    assert service.last_call == ("app", "CP-001", 1, DRIVER_ID, TENANT_ID)


def test_a_session_start_error_is_mapped_to_400():
    service = _FakeService(error=SessionStartError("charger CP-001 is offline"))
    client = TestClient(_build_app(service))

    response = client.post(
        "/charging/session/start/app",
        json={"charger_id": "CP-001", "connector_id": 1, "driver_id": str(DRIVER_ID)},
        headers={"X-Tenant-Id": str(TENANT_ID)},
    )

    assert response.status_code == 400
    assert "offline" in response.json()["detail"]


def test_qr_start_also_receives_the_tenant_id_from_the_header():
    service = _FakeService(result=_result())
    client = TestClient(_build_app(service))

    response = client.post(
        "/charging/session/start/qr",
        json={"token": "tok", "driver_id": str(DRIVER_ID), "secret": "s"},
        headers={"X-Tenant-Id": str(TENANT_ID)},
    )

    assert response.status_code == 200
    assert service.last_call == ("qr", "tok", DRIVER_ID, "s", TENANT_ID)

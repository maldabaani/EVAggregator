"""Tested against a real in-process upstream (not a mock) that reproduces
evagg.main's actual trust boundary — TenantContextMiddleware +
GatewaySignatureMiddleware — so these prove the signature this forwarder
produces is one the real middleware chain actually accepts.
"""

from __future__ import annotations

import uuid

import httpx
from fastapi import Depends, FastAPI
from starlette.testclient import TestClient

from evagg.core.tenancy import TenantContextMiddleware, require_current_tenant
from evagg.driver_app.session_start_forwarder import mount_session_start_forwarder
from evagg.gateway.jwt_tokens import create_access_token
from evagg.gateway.middleware import GatewaySignatureMiddleware

TENANT_ID = uuid.uuid4()
DRIVER_ID = uuid.uuid4()


def _build_upstream() -> FastAPI:
    app = FastAPI()

    @app.post("/charging/session/start/qr")
    async def start_qr(body: dict, tenant_id: uuid.UUID = Depends(require_current_tenant)) -> dict:
        return {"tenant_id": str(tenant_id), "driver_id": body["driver_id"], "token": body["token"]}

    @app.post("/charging/session/start/autocharge")
    async def start_autocharge(body: dict, tenant_id: uuid.UUID = Depends(require_current_tenant)) -> dict:
        return {"tenant_id": str(tenant_id), "mac_address": body["mac_address"]}

    @app.post("/charging/session/start/app")
    async def start_app(body: dict, tenant_id: uuid.UUID = Depends(require_current_tenant)) -> dict:
        return {"tenant_id": str(tenant_id), "driver_id": body["driver_id"], "charger_id": body["charger_id"]}

    @app.get("/charging/session/{session_id}/status")
    async def status(session_id: str, driver_id: str, tenant_id: uuid.UUID = Depends(require_current_tenant)) -> dict:
        return {"tenant_id": str(tenant_id), "session_id": session_id, "driver_id": driver_id}

    @app.get("/charging/session/{session_id}/live")
    async def live(session_id: str, driver_id: str, tenant_id: uuid.UUID = Depends(require_current_tenant)) -> dict:
        return {"tenant_id": str(tenant_id), "session_id": session_id, "driver_id": driver_id}

    @app.post("/charging/session/{session_id}/stop")
    async def stop(session_id: str, body: dict, tenant_id: uuid.UUID = Depends(require_current_tenant)) -> dict:
        return {"tenant_id": str(tenant_id), "session_id": session_id, "driver_id": body["driver_id"]}

    app.add_middleware(TenantContextMiddleware)
    app.add_middleware(GatewaySignatureMiddleware)
    return app


def _build_edge_app_with_forwarder() -> FastAPI:
    upstream = _build_upstream()
    app = FastAPI()
    mount_session_start_forwarder(app, "http://upstream", transport=httpx.ASGITransport(app=upstream))
    return app


def _auth_header(driver_id: uuid.UUID = DRIVER_ID, tenant_id: uuid.UUID = TENANT_ID) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(driver_id), tenant_id)}"}


def test_missing_bearer_token_is_rejected_before_reaching_upstream():
    client = TestClient(_build_edge_app_with_forwarder())

    response = client.post("/charging/session/start/qr", json={"token": "t", "driver_id": str(DRIVER_ID), "secret": "s"})

    assert response.status_code == 401


def test_malformed_bearer_token_is_rejected():
    client = TestClient(_build_edge_app_with_forwarder())

    response = client.post(
        "/charging/session/start/qr",
        json={"token": "t", "driver_id": str(DRIVER_ID), "secret": "s"},
        headers={"Authorization": "Bearer not-a-real-token"},
    )

    assert response.status_code == 401


def test_valid_token_is_signed_and_accepted_by_the_real_upstream_middleware_chain():
    client = TestClient(_build_edge_app_with_forwarder())

    response = client.post(
        "/charging/session/start/qr",
        json={"token": "t", "driver_id": str(DRIVER_ID), "secret": "s"},
        headers=_auth_header(),
    )

    assert response.status_code == 200
    assert response.json() == {"tenant_id": str(TENANT_ID), "driver_id": str(DRIVER_ID), "token": "t"}


def test_the_bodys_driver_id_is_overwritten_with_the_tokens_own_subject():
    """A driver cannot start a session as someone else just by editing the
    request body — the forwarder always substitutes its own verified
    driver_id before forwarding."""
    attacker_claimed_id = str(uuid.uuid4())
    client = TestClient(_build_edge_app_with_forwarder())

    response = client.post(
        "/charging/session/start/qr",
        json={"token": "t", "driver_id": attacker_claimed_id, "secret": "s"},
        headers=_auth_header(),
    )

    assert response.json()["driver_id"] == str(DRIVER_ID)
    assert response.json()["driver_id"] != attacker_claimed_id


def test_app_start_also_overwrites_the_bodys_driver_id():
    attacker_claimed_id = str(uuid.uuid4())
    client = TestClient(_build_edge_app_with_forwarder())

    response = client.post(
        "/charging/session/start/app",
        json={"charger_id": "CP-1", "connector_id": 1, "driver_id": attacker_claimed_id},
        headers=_auth_header(),
    )

    assert response.status_code == 200
    assert response.json()["driver_id"] == str(DRIVER_ID)
    assert response.json()["driver_id"] != attacker_claimed_id


def test_autocharge_forwards_without_needing_a_driver_id_field():
    client = TestClient(_build_edge_app_with_forwarder())

    response = client.post(
        "/charging/session/start/autocharge",
        json={"mac_address": "AA:BB:CC:DD:EE:FF", "charger_id": "CP-1"},
        headers=_auth_header(),
    )

    assert response.status_code == 200
    assert response.json() == {"tenant_id": str(TENANT_ID), "mac_address": "AA:BB:CC:DD:EE:FF"}


def test_an_unknown_start_method_returns_404():
    client = TestClient(_build_edge_app_with_forwarder())

    response = client.post("/charging/session/start/bogus", json={}, headers=_auth_header())

    assert response.status_code == 404


def test_a_caller_cannot_spoof_the_gateway_signature_directly():
    client = TestClient(_build_edge_app_with_forwarder())

    response = client.post(
        "/charging/session/start/autocharge",
        json={"mac_address": "AA:BB:CC:DD:EE:FF", "charger_id": "CP-1"},
        headers={**_auth_header(), "X-Gateway-Signature": "totally-bogus"},
    )

    assert response.status_code == 200


def test_two_drivers_with_different_tenants_are_forwarded_with_their_own_tenant():
    other_tenant = uuid.uuid4()
    other_driver = uuid.uuid4()
    client = TestClient(_build_edge_app_with_forwarder())

    response = client.post(
        "/charging/session/start/autocharge",
        json={"mac_address": "AA:BB:CC:DD:EE:FF", "charger_id": "CP-1"},
        headers=_auth_header(driver_id=other_driver, tenant_id=other_tenant),
    )

    assert response.json()["tenant_id"] == str(other_tenant)


def test_status_is_forwarded_with_the_verified_driver_id_as_a_query_param():
    client = TestClient(_build_edge_app_with_forwarder())

    response = client.get("/charging/session/session-1/status", headers=_auth_header())

    assert response.status_code == 200
    assert response.json() == {"tenant_id": str(TENANT_ID), "session_id": "session-1", "driver_id": str(DRIVER_ID)}


def test_status_requires_a_bearer_token():
    client = TestClient(_build_edge_app_with_forwarder())

    response = client.get("/charging/session/session-1/status")

    assert response.status_code == 401


def test_live_status_is_forwarded_with_the_verified_driver_id_as_a_query_param():
    client = TestClient(_build_edge_app_with_forwarder())

    response = client.get("/charging/session/session-1/live", headers=_auth_header())

    assert response.status_code == 200
    assert response.json() == {"tenant_id": str(TENANT_ID), "session_id": "session-1", "driver_id": str(DRIVER_ID)}


def test_live_status_requires_a_bearer_token():
    client = TestClient(_build_edge_app_with_forwarder())

    response = client.get("/charging/session/session-1/live")

    assert response.status_code == 401


def test_stop_is_forwarded_with_the_verified_driver_id_in_the_body():
    client = TestClient(_build_edge_app_with_forwarder())

    response = client.post("/charging/session/session-1/stop", headers=_auth_header())

    assert response.status_code == 200
    assert response.json() == {"tenant_id": str(TENANT_ID), "session_id": "session-1", "driver_id": str(DRIVER_ID)}


def test_stop_requires_a_bearer_token():
    client = TestClient(_build_edge_app_with_forwarder())

    response = client.post("/charging/session/session-1/stop")

    assert response.status_code == 401

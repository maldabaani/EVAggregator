"""Tested against a real in-process upstream reproducing evagg.main's
actual trust boundary, same as test_session_start_forwarder.py."""

from __future__ import annotations

import uuid

import httpx
from fastapi import Depends, FastAPI
from starlette.testclient import TestClient

from evagg.core.tenancy import TenantContextMiddleware, require_current_tenant
from evagg.driver_app.rewards_forwarder import mount_rewards_forwarder
from evagg.gateway.jwt_tokens import create_access_token
from evagg.gateway.middleware import GatewaySignatureMiddleware

TENANT_ID = uuid.uuid4()
DRIVER_ID = uuid.uuid4()
OTHER_DRIVER_ID = uuid.uuid4()


def _build_upstream() -> FastAPI:
    app = FastAPI()

    @app.get("/driver/rewards")
    async def get_rewards(driver_id: str, tenant_id: uuid.UUID = Depends(require_current_tenant)) -> dict:
        return {"driver_id": driver_id, "tenant_id": str(tenant_id), "balance": 50}

    @app.post("/driver/rewards/redeem")
    async def redeem(body: dict, tenant_id: uuid.UUID = Depends(require_current_tenant)) -> dict:
        return {"driver_id": body["driver_id"], "reward_id": body["reward_id"]}

    app.add_middleware(TenantContextMiddleware)
    app.add_middleware(GatewaySignatureMiddleware)
    return app


def _build_edge_app_with_forwarder() -> FastAPI:
    upstream = _build_upstream()
    app = FastAPI()
    mount_rewards_forwarder(app, "http://upstream", transport=httpx.ASGITransport(app=upstream))
    return app


def _auth_header(driver_id: uuid.UUID = DRIVER_ID, tenant_id: uuid.UUID = TENANT_ID) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(driver_id), tenant_id)}"}


def test_get_rewards_requires_a_bearer_token():
    client = TestClient(_build_edge_app_with_forwarder())

    response = client.get("/driver/rewards")

    assert response.status_code == 401


def test_get_rewards_is_scoped_to_the_authenticated_driver():
    client = TestClient(_build_edge_app_with_forwarder())

    response = client.get("/driver/rewards", headers=_auth_header())

    assert response.status_code == 200
    assert response.json()["driver_id"] == str(DRIVER_ID)


def test_redeem_always_uses_the_authenticated_drivers_own_id():
    client = TestClient(_build_edge_app_with_forwarder())

    response = client.post(
        "/driver/rewards/redeem",
        json={"driver_id": str(OTHER_DRIVER_ID), "reward_id": "free-coffee"},
        headers=_auth_header(),
    )

    assert response.status_code == 200
    assert response.json()["driver_id"] == str(DRIVER_ID)


def test_two_drivers_are_forwarded_with_their_own_identity():
    client = TestClient(_build_edge_app_with_forwarder())

    response = client.get("/driver/rewards", headers=_auth_header(driver_id=OTHER_DRIVER_ID))

    assert response.json()["driver_id"] == str(OTHER_DRIVER_ID)

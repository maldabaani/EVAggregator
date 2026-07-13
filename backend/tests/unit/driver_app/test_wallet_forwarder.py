"""Tested against a real in-process upstream reproducing evagg.main's
actual trust boundary, same as test_session_start_forwarder.py."""

from __future__ import annotations

import uuid

import httpx
from fastapi import Depends, FastAPI
from starlette.testclient import TestClient

from evagg.core.tenancy import TenantContextMiddleware, require_current_tenant
from evagg.driver_app.wallet_forwarder import mount_wallet_forwarder
from evagg.gateway.jwt_tokens import create_access_token
from evagg.gateway.middleware import GatewaySignatureMiddleware

TENANT_ID = uuid.uuid4()
DRIVER_ID = uuid.uuid4()
OTHER_DRIVER_ID = uuid.uuid4()


def _build_upstream() -> FastAPI:
    app = FastAPI()

    @app.get("/wallet/{wallet_id}/balance")
    async def balance(wallet_id: str, tenant_id: uuid.UUID = Depends(require_current_tenant)) -> dict:
        return {"wallet_id": wallet_id, "balance_minor_units": 1000}

    @app.post("/wallet/topup")
    async def topup(body: dict, tenant_id: uuid.UUID = Depends(require_current_tenant)) -> dict:
        return {"wallet_id": body["wallet_id"], "amount_minor_units": body["amount_minor_units"]}

    @app.get("/wallet/{wallet_id}/payment-method")
    async def get_method(wallet_id: str, tenant_id: uuid.UUID = Depends(require_current_tenant)) -> dict:
        return {"wallet_id": wallet_id, "data": None}

    @app.post("/wallet/{wallet_id}/payment-method")
    async def set_method(wallet_id: str, body: dict, tenant_id: uuid.UUID = Depends(require_current_tenant)) -> dict:
        return {"wallet_id": wallet_id, "type": body["type"]}

    app.add_middleware(TenantContextMiddleware)
    app.add_middleware(GatewaySignatureMiddleware)
    return app


def _build_edge_app_with_forwarder() -> FastAPI:
    upstream = _build_upstream()
    app = FastAPI()
    mount_wallet_forwarder(app, "http://upstream", transport=httpx.ASGITransport(app=upstream))
    return app


def _auth_header(driver_id: uuid.UUID = DRIVER_ID, tenant_id: uuid.UUID = TENANT_ID) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(driver_id), tenant_id)}"}


def test_balance_requires_a_bearer_token():
    client = TestClient(_build_edge_app_with_forwarder())

    response = client.get("/wallet/balance")

    assert response.status_code == 401


def test_balance_is_scoped_to_the_authenticated_drivers_own_wallet_id():
    client = TestClient(_build_edge_app_with_forwarder())

    response = client.get("/wallet/balance", headers=_auth_header())

    assert response.status_code == 200
    assert response.json()["wallet_id"] == str(DRIVER_ID)


def test_topup_always_uses_the_authenticated_drivers_own_wallet_id():
    """Even if a client tried to set a different wallet_id in the body, the
    forwarder always overwrites it — a driver can never top up (or later,
    read) another driver's wallet."""
    client = TestClient(_build_edge_app_with_forwarder())

    response = client.post(
        "/wallet/topup",
        json={"wallet_id": str(OTHER_DRIVER_ID), "psp_token": "tok-1", "amount_minor_units": 500, "currency": "AED"},
        headers=_auth_header(),
    )

    assert response.status_code == 200
    assert response.json()["wallet_id"] == str(DRIVER_ID)


def test_get_payment_method_is_scoped_to_the_authenticated_driver():
    client = TestClient(_build_edge_app_with_forwarder())

    response = client.get("/wallet/payment-method", headers=_auth_header())

    assert response.status_code == 200
    assert response.json()["wallet_id"] == str(DRIVER_ID)


def test_set_payment_method_is_scoped_to_the_authenticated_driver():
    client = TestClient(_build_edge_app_with_forwarder())

    response = client.post(
        "/wallet/payment-method", json={"type": "wallet_balance"}, headers=_auth_header()
    )

    assert response.status_code == 200
    assert response.json()["wallet_id"] == str(DRIVER_ID)


def test_two_different_drivers_are_forwarded_to_their_own_distinct_wallets():
    client = TestClient(_build_edge_app_with_forwarder())

    response = client.get("/wallet/balance", headers=_auth_header(driver_id=OTHER_DRIVER_ID))

    assert response.json()["wallet_id"] == str(OTHER_DRIVER_ID)

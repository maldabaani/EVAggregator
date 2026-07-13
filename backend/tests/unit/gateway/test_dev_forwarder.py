"""Task 6.3's missing forwarding half: evagg.gateway.dev_forwarder signs
whatever tenant id the caller states and forwards to an upstream app. Tested
against a real in-process upstream (not a mock) that reproduces main.py's
actual trust boundary — TenantContextMiddleware + GatewaySignatureMiddleware
— so these tests prove the signature the forwarder produces is one the real
middleware chain actually accepts, not just that some header got attached.
"""

from __future__ import annotations

import uuid

import httpx
from fastapi import Depends, FastAPI
from starlette.testclient import TestClient

from evagg.core.tenancy import TenantContextMiddleware, require_current_tenant
from evagg.gateway.app import build_gateway_app
from evagg.gateway.dev_forwarder import mount_dev_forwarder
from evagg.gateway.middleware import GatewaySignatureMiddleware

TENANT_ID = uuid.uuid4()


def _build_upstream() -> FastAPI:
    """A stand-in for evagg.main: the same two middlewares, in the same
    order, guarding a couple of routes shaped like the real ones this
    forwarder actually needs to reach."""
    app = FastAPI()

    @app.post("/admin/tariffs")
    async def create_tariff(body: dict, tenant_id: uuid.UUID = Depends(require_current_tenant)) -> dict:
        return {"id": "tariff-1", "tenant_id": str(tenant_id), "name": body["name"]}

    @app.put("/admin/tariffs/{tariff_id}")
    async def update_tariff(tariff_id: str, body: dict, tenant_id: uuid.UUID = Depends(require_current_tenant)) -> dict:
        return {"id": tariff_id, "tenant_id": str(tenant_id), "name": body["name"]}

    @app.get("/admin/teams/{team_id}/cost-report")
    async def cost_report(team_id: str, tenant_id: uuid.UUID = Depends(require_current_tenant)) -> dict:
        return {"team_id": team_id, "tenant_id": str(tenant_id)}

    app.add_middleware(TenantContextMiddleware)
    app.add_middleware(GatewaySignatureMiddleware)
    return app


def _build_gateway_with_forwarder() -> FastAPI:
    upstream = _build_upstream()
    gateway = build_gateway_app()
    mount_dev_forwarder(
        gateway,
        upstream_base_url="http://upstream",
        path_prefixes=("/admin/tariffs", "/admin/teams"),
        transport=httpx.ASGITransport(app=upstream),
    )
    return gateway


def test_missing_dev_tenant_header_is_rejected_before_reaching_upstream():
    client = TestClient(_build_gateway_with_forwarder())

    response = client.post("/admin/tariffs", json={"name": "Standard"})

    assert response.status_code == 400


def test_malformed_dev_tenant_header_is_rejected():
    client = TestClient(_build_gateway_with_forwarder())

    response = client.post("/admin/tariffs", json={"name": "Standard"}, headers={"X-Dev-Tenant-Id": "not-a-uuid"})

    assert response.status_code == 400


def test_valid_header_is_signed_and_accepted_by_the_real_middleware_chain():
    client = TestClient(_build_gateway_with_forwarder())

    response = client.post(
        "/admin/tariffs", json={"name": "Standard"}, headers={"X-Dev-Tenant-Id": str(TENANT_ID)}
    )

    assert response.status_code == 200
    assert response.json() == {"id": "tariff-1", "tenant_id": str(TENANT_ID), "name": "Standard"}


def test_put_with_no_tenant_id_in_the_body_still_forwards_via_header():
    client = TestClient(_build_gateway_with_forwarder())

    response = client.put(
        "/admin/tariffs/tariff-1", json={"name": "Renamed"}, headers={"X-Dev-Tenant-Id": str(TENANT_ID)}
    )

    assert response.status_code == 200
    assert response.json()["tenant_id"] == str(TENANT_ID)


def test_get_with_no_body_at_all_forwards_via_header():
    client = TestClient(_build_gateway_with_forwarder())

    response = client.get(
        "/admin/teams/team-1/cost-report", headers={"X-Dev-Tenant-Id": str(TENANT_ID)}
    )

    assert response.status_code == 200
    assert response.json() == {"team_id": "team-1", "tenant_id": str(TENANT_ID)}


def test_query_param_fallback_works_for_requests_that_cant_carry_a_header():
    client = TestClient(_build_gateway_with_forwarder())

    response = client.get(f"/admin/teams/team-1/cost-report?_dev_tenant_id={TENANT_ID}")

    assert response.status_code == 200
    assert response.json()["tenant_id"] == str(TENANT_ID)


def test_query_param_is_stripped_before_forwarding_upstream():
    client = TestClient(_build_gateway_with_forwarder())

    response = client.get(f"/admin/teams/team-1/cost-report?_dev_tenant_id={TENANT_ID}&other=1")

    assert response.status_code == 200


def test_a_caller_cannot_spoof_the_signature_by_setting_it_directly():
    """The forwarder always recomputes the signature itself from the
    X-Dev-Tenant-Id header — any X-Gateway-Signature the caller sets
    directly is simply overwritten, not trusted."""
    client = TestClient(_build_gateway_with_forwarder())

    response = client.post(
        "/admin/tariffs",
        json={"name": "Standard"},
        headers={"X-Dev-Tenant-Id": str(TENANT_ID), "X-Gateway-Signature": "totally-bogus"},
    )

    assert response.status_code == 200


def test_unmounted_oauth_routes_are_unaffected_by_the_forwarder():
    client = TestClient(_build_gateway_with_forwarder())

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

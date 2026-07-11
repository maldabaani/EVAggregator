"""Task 4.1 unit tests for the tenant-context middleware and super-admin
logging — isolated from any real DB connection."""

from __future__ import annotations

import logging
import uuid

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from evagg.core.tenancy import TenantContextMiddleware, current_tenant_id, log_superadmin_access


async def _echo_tenant(request):
    return JSONResponse({"tenant_id": str(current_tenant_id.get())})


def _build_app() -> Starlette:
    app = Starlette(routes=[Route("/whoami", _echo_tenant)])
    app.add_middleware(TenantContextMiddleware)
    return app


def test_request_without_tenant_header_is_rejected():
    client = TestClient(_build_app())
    response = client.get("/whoami")
    assert response.status_code == 401


def test_request_with_malformed_tenant_header_is_rejected():
    client = TestClient(_build_app())
    response = client.get("/whoami", headers={"x-tenant-id": "not-a-uuid"})
    assert response.status_code == 401


def test_request_with_valid_tenant_header_resolves_context():
    tenant_id = uuid.uuid4()
    client = TestClient(_build_app())
    response = client.get("/whoami", headers={"x-tenant-id": str(tenant_id)})
    assert response.status_code == 200
    assert response.json()["tenant_id"] == str(tenant_id)


def test_healthz_exempt_from_tenant_requirement():
    async def health(request):
        return JSONResponse({"status": "ok"})

    app = Starlette(routes=[Route("/healthz", health)])
    app.add_middleware(TenantContextMiddleware)
    client = TestClient(app)

    response = client.get("/healthz")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_superadmin_bypass_access_is_logged(caplog):
    with caplog.at_level(logging.WARNING, logger="evagg.tenancy"):
        await log_superadmin_access(actor="ops-alice", reason="incident-1234", table="wallet_ledger")

    assert any(r.message == "superadmin_bypass_access" for r in caplog.records)
    logged = next(r for r in caplog.records if r.message == "superadmin_bypass_access")
    assert logged.actor == "ops-alice"
    assert logged.reason == "incident-1234"
    assert logged.table == "wallet_ledger"

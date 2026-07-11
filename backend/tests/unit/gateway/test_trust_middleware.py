import uuid

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from evagg.gateway.middleware import GatewaySignatureMiddleware
from evagg.gateway.trust import SIGNATURE_HEADER, sign_tenant_id


async def _echo(request):
    return JSONResponse({"ok": True})


def _build_app() -> Starlette:
    app = Starlette(routes=[Route("/whoami", _echo)])
    app.add_middleware(GatewaySignatureMiddleware)
    return app


def test_correctly_signed_tenant_header_is_accepted():
    tenant_id = uuid.uuid4()
    client = TestClient(_build_app())

    response = client.get(
        "/whoami",
        headers={"x-tenant-id": str(tenant_id), SIGNATURE_HEADER: sign_tenant_id(tenant_id)},
    )

    assert response.status_code == 200


def test_spoofed_tenant_header_without_signature_is_rejected():
    tenant_id = uuid.uuid4()
    client = TestClient(_build_app())

    response = client.get("/whoami", headers={"x-tenant-id": str(tenant_id)})

    assert response.status_code == 403


def test_spoofed_tenant_header_with_wrong_signature_is_rejected():
    tenant_id = uuid.uuid4()
    client = TestClient(_build_app())

    response = client.get(
        "/whoami", headers={"x-tenant-id": str(tenant_id), SIGNATURE_HEADER: "not-a-real-signature"}
    )

    assert response.status_code == 403


def test_signature_for_a_different_tenant_is_rejected():
    tenant_id = uuid.uuid4()
    other_tenant_id = uuid.uuid4()
    client = TestClient(_build_app())

    response = client.get(
        "/whoami",
        headers={"x-tenant-id": str(tenant_id), SIGNATURE_HEADER: sign_tenant_id(other_tenant_id)},
    )

    assert response.status_code == 403

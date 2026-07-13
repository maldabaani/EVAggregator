import uuid

from fastapi import Depends, FastAPI
from starlette.testclient import TestClient

from evagg.gateway.jwt_tokens import create_access_token
from evagg.identity.driver_session import DriverIdentity, require_driver_identity


def _build_app():
    app = FastAPI()

    @app.get("/whoami")
    async def whoami(identity: DriverIdentity = Depends(require_driver_identity)) -> dict:
        return {"driver_id": str(identity.driver_id), "tenant_id": str(identity.tenant_id)}

    return app


def test_a_valid_token_resolves_the_driver_and_tenant_ids():
    driver_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    token = create_access_token(str(driver_id), tenant_id)
    client = TestClient(_build_app())

    response = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {"driver_id": str(driver_id), "tenant_id": str(tenant_id)}


def test_missing_authorization_header_is_rejected():
    client = TestClient(_build_app())

    response = client.get("/whoami")

    assert response.status_code == 401


def test_non_bearer_authorization_header_is_rejected():
    client = TestClient(_build_app())

    response = client.get("/whoami", headers={"Authorization": "Basic dXNlcjpwYXNz"})

    assert response.status_code == 401


def test_malformed_token_is_rejected():
    client = TestClient(_build_app())

    response = client.get("/whoami", headers={"Authorization": "Bearer not-a-real-token"})

    assert response.status_code == 401

import secrets
import uuid

from starlette.testclient import TestClient

from evagg.gateway.app import build_gateway_app
from evagg.gateway.jwt_tokens import decode_access_token
from evagg.gateway.pkce import compute_code_challenge
from evagg.gateway.sso import SSOIdentity


class _StubSSOProvider:
    def __init__(self, identity: SSOIdentity) -> None:
        self._identity = identity

    def authenticate(self, credential: str) -> SSOIdentity:
        if credential != "valid-credential":
            from evagg.gateway.sso import SSOError

            raise SSOError("invalid credential")
        return self._identity


def _pkce_login(client: TestClient, tenant_id: uuid.UUID, subject: str = "driver-1") -> dict:
    verifier = secrets.token_urlsafe(32)
    challenge = compute_code_challenge(verifier)

    auth_response = client.post(
        "/oauth/authorize",
        json={"subject": subject, "tenant_id": str(tenant_id), "code_challenge": challenge},
    )
    assert auth_response.status_code == 200
    code = auth_response.json()["code"]

    token_response = client.post(
        "/oauth/token",
        json={"grant_type": "authorization_code", "code": code, "code_verifier": verifier},
    )
    assert token_response.status_code == 200
    return token_response.json()


def test_pkce_auth_flow_issues_valid_jwt():
    tenant_id = uuid.uuid4()
    client = TestClient(build_gateway_app())

    tokens = _pkce_login(client, tenant_id)

    claims = decode_access_token(tokens["access_token"])
    assert claims["sub"] == "driver-1"
    assert claims["tenant_id"] == str(tenant_id)


def test_pkce_flow_rejects_wrong_code_verifier():
    tenant_id = uuid.uuid4()
    client = TestClient(build_gateway_app())
    challenge = compute_code_challenge(secrets.token_urlsafe(32))

    auth_response = client.post(
        "/oauth/authorize",
        json={"subject": "driver-1", "tenant_id": str(tenant_id), "code_challenge": challenge},
    )
    code = auth_response.json()["code"]

    token_response = client.post(
        "/oauth/token",
        json={"grant_type": "authorization_code", "code": code, "code_verifier": "wrong-verifier"},
    )

    assert token_response.status_code == 400


def test_refresh_token_rotation_invalidates_old_token():
    tenant_id = uuid.uuid4()
    client = TestClient(build_gateway_app())
    tokens = _pkce_login(client, tenant_id)

    refreshed = client.post(
        "/oauth/token", json={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]}
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] != tokens["refresh_token"]

    reused = client.post(
        "/oauth/token", json={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]}
    )
    assert reused.status_code == 401


def test_rate_limit_exceeded_returns_429():
    tenant_id = uuid.uuid4()
    from evagg.gateway.rate_limit import InMemoryRateLimiter

    app = build_gateway_app(rate_limiter=InMemoryRateLimiter())
    client = TestClient(app)

    from evagg.core.config import settings

    for _ in range(settings.rate_limit_requests_per_window):
        _pkce_login(client, tenant_id)

    verifier = secrets.token_urlsafe(32)
    challenge = compute_code_challenge(verifier)
    auth_response = client.post(
        "/oauth/authorize",
        json={"subject": "driver-1", "tenant_id": str(tenant_id), "code_challenge": challenge},
    )
    code = auth_response.json()["code"]
    over_limit_response = client.post(
        "/oauth/token",
        json={"grant_type": "authorization_code", "code": code, "code_verifier": verifier},
    )

    assert over_limit_response.status_code == 429


def test_sso_login_authenticates_via_configured_idp_and_issues_jwt():
    tenant_id = uuid.uuid4()
    provider = _StubSSOProvider(SSOIdentity(subject_id="okta|user-1", email="alice@example.com"))
    app = build_gateway_app(sso_providers={"okta": provider})
    client = TestClient(app)

    response = client.post(
        "/sso/okta/callback", json={"tenant_id": str(tenant_id), "credential": "valid-credential"}
    )

    assert response.status_code == 200
    claims = decode_access_token(response.json()["access_token"])
    assert claims["sub"] == "okta|user-1"
    assert claims["tenant_id"] == str(tenant_id)


def test_sso_login_with_invalid_credential_is_rejected():
    provider = _StubSSOProvider(SSOIdentity(subject_id="okta|user-1"))
    app = build_gateway_app(sso_providers={"okta": provider})
    client = TestClient(app)

    response = client.post(
        "/sso/okta/callback", json={"tenant_id": str(uuid.uuid4()), "credential": "bad-credential"}
    )

    assert response.status_code == 401


def test_unknown_sso_provider_returns_404():
    app = build_gateway_app(sso_providers={})
    client = TestClient(app)

    response = client.post(
        "/sso/unknown/callback", json={"tenant_id": str(uuid.uuid4()), "credential": "x"}
    )

    assert response.status_code == 404

import uuid

import jwt
import pytest

from evagg.gateway.jwt_tokens import TokenError, create_access_token, decode_access_token


def test_created_token_decodes_with_expected_claims():
    tenant_id = uuid.uuid4()
    token = create_access_token(subject="driver-1", tenant_id=tenant_id)

    claims = decode_access_token(token)

    assert claims["sub"] == "driver-1"
    assert claims["tenant_id"] == str(tenant_id)
    assert "jti" in claims


def test_expired_token_is_rejected():
    token = create_access_token(subject="driver-1", tenant_id=uuid.uuid4(), ttl_seconds=-10)

    with pytest.raises(TokenError):
        decode_access_token(token)


def test_tampered_signature_is_rejected():
    token = create_access_token(subject="driver-1", tenant_id=uuid.uuid4())
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")

    with pytest.raises(TokenError):
        decode_access_token(tampered)


def test_wrong_secret_is_rejected():
    tenant_id = uuid.uuid4()
    token = jwt.encode({"sub": "x", "tenant_id": str(tenant_id)}, "some-other-secret", algorithm="HS256")

    with pytest.raises(TokenError):
        decode_access_token(token)

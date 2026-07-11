from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from evagg.gateway.sso import OIDCProvider, SAMLProvider, SSOError


@pytest.fixture
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return private_key, public_key


def _pem(key) -> bytes:
    from cryptography.hazmat.primitives import serialization

    if hasattr(key, "private_bytes"):
        return key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    return key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def test_valid_id_token_from_configured_idp_authenticates(rsa_keypair):
    private_key, public_key = rsa_keypair
    id_token = jwt.encode(
        {
            "sub": "okta|user-123",
            "email": "alice@example.com",
            "iss": "https://idp.example.com",
            "aud": "evagg-portal",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        _pem(private_key),
        algorithm="RS256",
        headers={"kid": "key-1"},
    )
    provider = OIDCProvider(
        issuer="https://idp.example.com",
        audience="evagg-portal",
        key_resolver=lambda kid: _pem(public_key),
    )

    identity = provider.authenticate(id_token)

    assert identity.subject_id == "okta|user-123"
    assert identity.email == "alice@example.com"


def test_id_token_with_wrong_issuer_is_rejected(rsa_keypair):
    private_key, public_key = rsa_keypair
    id_token = jwt.encode(
        {
            "sub": "user-1",
            "iss": "https://attacker.example.com",
            "aud": "evagg-portal",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        _pem(private_key),
        algorithm="RS256",
        headers={"kid": "key-1"},
    )
    provider = OIDCProvider(
        issuer="https://idp.example.com",
        audience="evagg-portal",
        key_resolver=lambda kid: _pem(public_key),
    )

    with pytest.raises(SSOError):
        provider.authenticate(id_token)


def test_expired_id_token_is_rejected(rsa_keypair):
    private_key, public_key = rsa_keypair
    id_token = jwt.encode(
        {
            "sub": "user-1",
            "iss": "https://idp.example.com",
            "aud": "evagg-portal",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
        },
        _pem(private_key),
        algorithm="RS256",
        headers={"kid": "key-1"},
    )
    provider = OIDCProvider(
        issuer="https://idp.example.com",
        audience="evagg-portal",
        key_resolver=lambda kid: _pem(public_key),
    )

    with pytest.raises(SSOError):
        provider.authenticate(id_token)


_SAML_TEMPLATE = """<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:Assertion>
    <saml:Issuer>{issuer}</saml:Issuer>
    <saml:Subject><saml:NameID>{name_id}</saml:NameID></saml:Subject>
    <saml:Conditions NotOnOrAfter="{not_on_or_after}"/>
  </saml:Assertion>
</samlp:Response>"""


def test_saml_assertion_with_matching_issuer_authenticates():
    xml = _SAML_TEMPLATE.format(
        issuer="https://idp.example.com",
        name_id="bob@example.com",
        not_on_or_after=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
    )
    provider = SAMLProvider(issuer="https://idp.example.com")

    identity = provider.authenticate(xml)

    assert identity.subject_id == "bob@example.com"


def test_saml_assertion_with_wrong_issuer_is_rejected():
    xml = _SAML_TEMPLATE.format(
        issuer="https://not-the-idp.example.com",
        name_id="bob@example.com",
        not_on_or_after=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
    )
    provider = SAMLProvider(issuer="https://idp.example.com")

    with pytest.raises(SSOError):
        provider.authenticate(xml)


def test_expired_saml_assertion_is_rejected():
    xml = _SAML_TEMPLATE.format(
        issuer="https://idp.example.com",
        name_id="bob@example.com",
        not_on_or_after=(datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
    )
    provider = SAMLProvider(issuer="https://idp.example.com")

    with pytest.raises(SSOError):
        provider.authenticate(xml)

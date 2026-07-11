from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from evagg.charging_auth.plug_and_charge import (
    InMemoryEmaidDriverMap,
    PlugAndChargeError,
    PlugAndChargeValidator,
)

TRUSTED_ISSUER = "https://oem-ca.example.com"


def _pem(key, private: bool) -> str:
    if private:
        return key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
    return key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


@pytest.fixture
def trusted_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def _make_cert(private_key, issuer: str, emaid: str | None = "EMAID-ABC123", expired: bool = False) -> str:
    claims = {
        "iss": issuer,
        "exp": datetime.now(timezone.utc) + (timedelta(minutes=-5) if expired else timedelta(minutes=5)),
    }
    if emaid is not None:
        claims["emaid"] = emaid
    return jwt.encode(claims, _pem(private_key, private=True), algorithm="RS256")


@pytest.mark.asyncio
async def test_plug_and_charge_valid_cert_resolves_to_correct_driver(trusted_keypair):
    private_key, public_key = trusted_keypair
    emaid_map = InMemoryEmaidDriverMap()
    driver_id = uuid.uuid4()
    emaid_map.register("EMAID-ABC123", driver_id)
    validator = PlugAndChargeValidator({TRUSTED_ISSUER: _pem(public_key, private=False)}, emaid_map)
    cert = _make_cert(private_key, TRUSTED_ISSUER)

    resolved_driver_id = await validator.resolve_driver_from_cert(cert)

    assert resolved_driver_id == driver_id


@pytest.mark.asyncio
async def test_plug_and_charge_invalid_cert_rejected_and_falls_back(trusted_keypair):
    private_key, _ = trusted_keypair
    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    emaid_map = InMemoryEmaidDriverMap()
    emaid_map.register("EMAID-ABC123", uuid.uuid4())
    # Validator only trusts the real CA's public key, not the attacker's.
    validator = PlugAndChargeValidator(
        {TRUSTED_ISSUER: _pem(private_key.public_key(), private=False)}, emaid_map
    )
    forged_cert = _make_cert(attacker_key, TRUSTED_ISSUER)

    with pytest.raises(PlugAndChargeError):
        await validator.resolve_driver_from_cert(forged_cert)


@pytest.mark.asyncio
async def test_expired_cert_rejected(trusted_keypair):
    private_key, public_key = trusted_keypair
    emaid_map = InMemoryEmaidDriverMap()
    emaid_map.register("EMAID-ABC123", uuid.uuid4())
    validator = PlugAndChargeValidator({TRUSTED_ISSUER: _pem(public_key, private=False)}, emaid_map)
    expired_cert = _make_cert(private_key, TRUSTED_ISSUER, expired=True)

    with pytest.raises(PlugAndChargeError):
        await validator.resolve_driver_from_cert(expired_cert)


@pytest.mark.asyncio
async def test_cert_with_unmapped_emaid_rejected(trusted_keypair):
    private_key, public_key = trusted_keypair
    emaid_map = InMemoryEmaidDriverMap()  # no EMAID registered at all
    validator = PlugAndChargeValidator({TRUSTED_ISSUER: _pem(public_key, private=False)}, emaid_map)
    cert = _make_cert(private_key, TRUSTED_ISSUER, emaid="EMAID-UNKNOWN")

    with pytest.raises(PlugAndChargeError, match="no driver account mapped"):
        await validator.resolve_driver_from_cert(cert)

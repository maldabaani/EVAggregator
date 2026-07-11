from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from evagg.charging_auth.plug_and_charge import (
    InMemoryEmaidDriverMap,
    InMemoryOcspChecker,
    PlugAndChargeError,
    PlugAndChargeValidator,
)
from charging_auth.x509_test_helpers import make_ca_cert, make_leaf_cert, pem


@pytest.fixture
def ca_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, make_ca_cert(private_key)


@pytest.mark.asyncio
async def test_plug_and_charge_valid_cert_resolves_to_correct_driver(ca_keypair):
    ca_key, ca_cert = ca_keypair
    vehicle_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    emaid_map = InMemoryEmaidDriverMap()
    driver_id = uuid.uuid4()
    emaid_map.register("EMAID-ABC123", driver_id)
    validator = PlugAndChargeValidator([pem(ca_cert)], emaid_map)
    cert = make_leaf_cert(ca_key, ca_cert, vehicle_key.public_key())

    resolved_driver_id = await validator.resolve_driver_from_cert(pem(cert))

    assert resolved_driver_id == driver_id


@pytest.mark.asyncio
async def test_forged_cert_rejected_even_though_issuer_name_matches(ca_keypair):
    _, ca_cert = ca_keypair
    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    vehicle_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    emaid_map = InMemoryEmaidDriverMap()
    emaid_map.register("EMAID-ABC123", uuid.uuid4())
    # Validator only trusts the real CA cert, not the attacker's key —
    # forging a cert whose issuer *name* matches isn't enough; the
    # signature itself must verify against the trusted CA's public key.
    validator = PlugAndChargeValidator([pem(ca_cert)], emaid_map)
    forged_cert = make_leaf_cert(attacker_key, ca_cert, vehicle_key.public_key())

    with pytest.raises(PlugAndChargeError, match="not signed by any trusted CA"):
        await validator.resolve_driver_from_cert(pem(forged_cert))


@pytest.mark.asyncio
async def test_expired_cert_rejected(ca_keypair):
    ca_key, ca_cert = ca_keypair
    vehicle_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    emaid_map = InMemoryEmaidDriverMap()
    emaid_map.register("EMAID-ABC123", uuid.uuid4())
    validator = PlugAndChargeValidator([pem(ca_cert)], emaid_map)
    now = datetime.now(timezone.utc)
    expired_cert = make_leaf_cert(
        ca_key, ca_cert, vehicle_key.public_key(), not_before=now - timedelta(days=10), not_after=now - timedelta(days=5)
    )

    with pytest.raises(PlugAndChargeError, match="validity period"):
        await validator.resolve_driver_from_cert(pem(expired_cert))


@pytest.mark.asyncio
async def test_not_yet_valid_cert_rejected(ca_keypair):
    ca_key, ca_cert = ca_keypair
    vehicle_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    emaid_map = InMemoryEmaidDriverMap()
    emaid_map.register("EMAID-ABC123", uuid.uuid4())
    validator = PlugAndChargeValidator([pem(ca_cert)], emaid_map)
    now = datetime.now(timezone.utc)
    future_cert = make_leaf_cert(
        ca_key, ca_cert, vehicle_key.public_key(), not_before=now + timedelta(days=5), not_after=now + timedelta(days=10)
    )

    with pytest.raises(PlugAndChargeError, match="validity period"):
        await validator.resolve_driver_from_cert(pem(future_cert))


@pytest.mark.asyncio
async def test_cert_with_unmapped_emaid_rejected(ca_keypair):
    ca_key, ca_cert = ca_keypair
    vehicle_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    emaid_map = InMemoryEmaidDriverMap()  # no EMAID registered at all
    validator = PlugAndChargeValidator([pem(ca_cert)], emaid_map)
    cert = make_leaf_cert(ca_key, ca_cert, vehicle_key.public_key(), emaid="EMAID-UNKNOWN")

    with pytest.raises(PlugAndChargeError, match="no driver account mapped"):
        await validator.resolve_driver_from_cert(pem(cert))


@pytest.mark.asyncio
async def test_cert_missing_emaid_rejected(ca_keypair):
    ca_key, ca_cert = ca_keypair
    vehicle_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    emaid_map = InMemoryEmaidDriverMap()
    validator = PlugAndChargeValidator([pem(ca_cert)], emaid_map)
    cert = make_leaf_cert(ca_key, ca_cert, vehicle_key.public_key(), emaid=None)

    with pytest.raises(PlugAndChargeError, match="missing EMAID"):
        await validator.resolve_driver_from_cert(pem(cert))


@pytest.mark.asyncio
async def test_revoked_cert_rejected_via_ocsp_checker(ca_keypair):
    ca_key, ca_cert = ca_keypair
    vehicle_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    emaid_map = InMemoryEmaidDriverMap()
    emaid_map.register("EMAID-ABC123", uuid.uuid4())
    cert = make_leaf_cert(ca_key, ca_cert, vehicle_key.public_key())

    ocsp = InMemoryOcspChecker()
    ocsp.revoke(cert.serial_number)
    validator = PlugAndChargeValidator([pem(ca_cert)], emaid_map, ocsp_checker=ocsp)

    with pytest.raises(PlugAndChargeError, match="revoked"):
        await validator.resolve_driver_from_cert(pem(cert))


@pytest.mark.asyncio
async def test_non_revoked_cert_accepted_via_ocsp_checker(ca_keypair):
    ca_key, ca_cert = ca_keypair
    vehicle_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    emaid_map = InMemoryEmaidDriverMap()
    driver_id = uuid.uuid4()
    emaid_map.register("EMAID-ABC123", driver_id)
    cert = make_leaf_cert(ca_key, ca_cert, vehicle_key.public_key())

    ocsp = InMemoryOcspChecker()  # nothing revoked
    validator = PlugAndChargeValidator([pem(ca_cert)], emaid_map, ocsp_checker=ocsp)

    assert await validator.resolve_driver_from_cert(pem(cert)) == driver_id


@pytest.mark.asyncio
async def test_malformed_certificate_rejected(ca_keypair):
    _, ca_cert = ca_keypair
    emaid_map = InMemoryEmaidDriverMap()
    validator = PlugAndChargeValidator([pem(ca_cert)], emaid_map)

    with pytest.raises(PlugAndChargeError, match="malformed"):
        await validator.resolve_driver_from_cert("not a real certificate")

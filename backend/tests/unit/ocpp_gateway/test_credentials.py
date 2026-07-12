import pytest

from evagg.ocpp_gateway.credentials import InMemoryCredentialVerifier, hash_credential, verify_credential


def test_correct_secret_verifies_against_hash():
    stored = hash_credential("s3cret")
    assert verify_credential("s3cret", stored)


def test_wrong_secret_fails_verification():
    stored = hash_credential("s3cret")
    assert not verify_credential("wrong", stored)


def test_malformed_stored_hash_fails_closed():
    assert not verify_credential("s3cret", "not-a-valid-hash")


@pytest.mark.asyncio
async def test_in_memory_verifier_rejects_unknown_charger():
    verifier = InMemoryCredentialVerifier()
    assert not await verifier.verify("unknown-charger", "anything")


@pytest.mark.asyncio
async def test_in_memory_verifier_accepts_correct_credential():
    verifier = InMemoryCredentialVerifier({"CP-1": "s3cret"})
    assert await verifier.verify("CP-1", "s3cret")
    assert not await verifier.verify("CP-1", "wrong")

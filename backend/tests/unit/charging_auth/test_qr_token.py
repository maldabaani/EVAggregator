from __future__ import annotations

import pytest

from evagg.charging_auth.qr_token import QrTokenError, sign_qr_token, verify_qr_token

SECRET = "shared-gateway-secret"


def test_valid_qr_token_starts_correct_session():
    token = sign_qr_token("CP-001", 1, SECRET, ttl_seconds=300, issued_at=1_000_000.0)

    payload = verify_qr_token(token, SECRET, now=1_000_100.0)  # 100s later, within TTL

    assert payload.charger_id == "CP-001"
    assert payload.connector_id == 1


def test_expired_qr_token_rejected_with_clear_error():
    token = sign_qr_token("CP-001", 1, SECRET, ttl_seconds=300, issued_at=1_000_000.0)

    with pytest.raises(QrTokenError, match="expired"):
        verify_qr_token(token, SECRET, now=1_000_301.0)  # 1s past the 300s TTL


def test_tampered_qr_token_rejected():
    token = sign_qr_token("CP-001", 1, SECRET, issued_at=1_000_000.0)
    payload_b64, signature = token.split(".", 1)
    # Flip a character in the payload so the signature no longer matches,
    # simulating an attacker altering the charger_id/connector_id.
    tampered_payload = payload_b64[:-1] + ("A" if payload_b64[-1] != "A" else "B")
    tampered = f"{tampered_payload}.{signature}"

    with pytest.raises(QrTokenError):
        verify_qr_token(tampered, SECRET, now=1_000_010.0)


def test_qr_token_signed_with_wrong_secret_rejected():
    token = sign_qr_token("CP-001", 1, "wrong-secret", issued_at=1_000_000.0)

    with pytest.raises(QrTokenError):
        verify_qr_token(token, SECRET, now=1_000_010.0)


def test_malformed_qr_token_rejected():
    with pytest.raises(QrTokenError):
        verify_qr_token("not-a-real-token", SECRET)

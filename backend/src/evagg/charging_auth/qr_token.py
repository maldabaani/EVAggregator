"""Task 5.2 — QR session start. The QR encodes `{charger_id, connector_id}`
as a signed, short-lived token (HMAC, not a bare JSON payload) so printing a
fake QR can't spoof a charger — the app decodes it, then the backend
independently re-verifies the signature and expiry before ever issuing
`RemoteStartTransaction`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass


class QrTokenError(Exception):
    pass


@dataclass(frozen=True)
class QrTokenPayload:
    charger_id: str
    connector_id: int


def sign_qr_token(
    charger_id: str,
    connector_id: int,
    secret: str,
    ttl_seconds: int = 300,
    issued_at: float | None = None,
) -> str:
    issued_at = issued_at if issued_at is not None else time.time()
    payload = {
        "charger_id": charger_id,
        "connector_id": connector_id,
        "issued_at": issued_at,
        "ttl": ttl_seconds,
    }
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("ascii")
    signature = hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"


def verify_qr_token(token: str, secret: str, now: float | None = None) -> QrTokenPayload:
    now = now if now is not None else time.time()

    try:
        payload_b64, signature = token.split(".", 1)
    except ValueError as exc:
        raise QrTokenError("malformed QR token") from exc

    expected_signature = hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_signature, signature):
        raise QrTokenError("invalid or tampered QR token")

    try:
        payload = json.loads(base64.urlsafe_b64decode(payload_b64.encode("ascii")))
    except Exception as exc:
        raise QrTokenError("malformed QR token payload") from exc

    if now > payload["issued_at"] + payload["ttl"]:
        raise QrTokenError("QR token has expired")

    return QrTokenPayload(charger_id=payload["charger_id"], connector_id=payload["connector_id"])

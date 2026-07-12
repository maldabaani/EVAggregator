"""Per-charger WebSocket credential hashing/verification (Task 2.1 — Basic
Auth for OCPP 1.6J chargers; 2.0.1 chargers additionally support TLS client
certs, negotiated at the transport layer ahead of this check).
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Protocol


def hash_credential(secret: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, 100_000)
    return f"pbkdf2${salt.hex()}${derived.hex()}"


def verify_credential(secret: str, stored_hash: str) -> bool:
    try:
        scheme, salt_hex, derived_hex = stored_hash.split("$")
    except ValueError:
        return False
    if scheme != "pbkdf2":
        return False
    salt = bytes.fromhex(salt_hex)
    expected = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, 100_000)
    return hmac.compare_digest(expected.hex(), derived_hex)


class CredentialVerifier(Protocol):
    async def verify(self, charger_id: str, credential: str) -> bool: ...


class InMemoryCredentialVerifier:
    """Reference implementation for unit tests / local dev."""

    def __init__(self, credentials_by_charger: dict[str, str] | None = None) -> None:
        # charger_id -> plaintext credential, hashed on insert
        self._hashes: dict[str, str] = {
            charger_id: hash_credential(secret) for charger_id, secret in (credentials_by_charger or {}).items()
        }

    def set_credential(self, charger_id: str, secret: str) -> None:
        self._hashes[charger_id] = hash_credential(secret)

    async def verify(self, charger_id: str, credential: str) -> bool:
        stored = self._hashes.get(charger_id)
        if stored is None:
            return False
        return verify_credential(credential, stored)

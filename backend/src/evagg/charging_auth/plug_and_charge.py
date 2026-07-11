"""Task 5.2 — Plug & Charge (ISO 15118): validates the vehicle's certificate
against a trusted CA list and maps its EMAID to a driver account.

Real ISO 15118 uses X.509 certificate chains + OCSP revocation checking —
the backlog itself flags this as the largest integration risk of the three
auth methods, "dependent on the vehicle/OEM ecosystem." This models the
cert as a CA-signed token (same signature-verification shape as Task 1.3's
OIDC provider: verify against a trusted issuer's key, check expiry, resolve
an identity claim) so the platform-side logic this task actually owns —
signature verification against configured trusted issuers, EMAID -> driver
resolution, reject-and-fall-back on failure — is implemented and tested for
real. Full X.509 chain/OCSP validation is a follow-up once a real vehicle/
OEM cert authority is integrated.
"""

from __future__ import annotations

import uuid
from typing import Protocol

import jwt


class PlugAndChargeError(Exception):
    pass


class EmaidDriverMap(Protocol):
    async def get_driver_id_for_emaid(self, emaid: str) -> uuid.UUID | None: ...


class InMemoryEmaidDriverMap:
    def __init__(self) -> None:
        self._mapping: dict[str, uuid.UUID] = {}

    def register(self, emaid: str, driver_id: uuid.UUID) -> None:
        self._mapping[emaid] = driver_id

    async def get_driver_id_for_emaid(self, emaid: str) -> uuid.UUID | None:
        return self._mapping.get(emaid)


class PlugAndChargeValidator:
    def __init__(self, trusted_issuers: dict[str, str], emaid_map: EmaidDriverMap) -> None:
        """`trusted_issuers` maps issuer name -> PEM public key, standing in
        for the trusted CA list."""
        self._trusted_issuers = trusted_issuers
        self._emaid_map = emaid_map

    async def resolve_driver_from_cert(self, cert_token: str) -> uuid.UUID:
        last_error: Exception | None = None
        for issuer, public_key_pem in self._trusted_issuers.items():
            try:
                claims = jwt.decode(
                    cert_token,
                    public_key_pem,
                    algorithms=["RS256"],
                    issuer=issuer,
                    options={"require": ["exp", "iss"]},
                )
            except jwt.PyJWTError as exc:
                last_error = exc
                continue

            emaid = claims.get("emaid")
            if not emaid:
                raise PlugAndChargeError("certificate missing EMAID claim")

            driver_id = await self._emaid_map.get_driver_id_for_emaid(emaid)
            if driver_id is None:
                raise PlugAndChargeError(f"no driver account mapped for EMAID {emaid}")
            return driver_id

        raise PlugAndChargeError("certificate not signed by any trusted issuer") from last_error

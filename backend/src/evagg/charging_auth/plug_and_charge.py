"""Task 5.2 — Plug & Charge (ISO 15118): validates the vehicle's contract
certificate against a trusted CA and maps its EMAID to a driver account.

Real ISO 15118 validates a full certificate chain (leaf -> sub-CA -> root)
plus OCSP/CRL revocation checking. This validates a single-level chain — the
presented contract certificate must be signed directly by one of the
configured trusted CAs — and models revocation checking behind an
injectable `OcspChecker` rather than calling a live OCSP responder (no real
OEM CA is integrated yet). A full multi-level chain builder is a follow-up
once a real vehicle/OEM cert authority is integrated; the platform-side
logic this task owns — signature verification against a trusted CA,
validity-period and revocation checks, EMAID -> driver resolution, and
reject-and-fall-back on any failure — is implemented and tested for real
X.509 certificates.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Callable, Protocol

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.x509.oid import NameOID


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


class OcspChecker(Protocol):
    """Stands in for a real OCSP responder call. A revoked contract
    certificate is otherwise indistinguishable from a valid one — signature
    and validity-period checks alone would accept it."""

    async def is_revoked(self, serial_number: int) -> bool: ...


class InMemoryOcspChecker:
    def __init__(self) -> None:
        self._revoked: set[int] = set()

    def revoke(self, serial_number: int) -> None:
        self._revoked.add(serial_number)

    async def is_revoked(self, serial_number: int) -> bool:
        return serial_number in self._revoked


def _signed_by(cert: x509.Certificate, ca_cert: x509.Certificate) -> bool:
    """Verifies `cert` was signed by `ca_cert`'s private key: both that the
    issuer name matches the CA's subject *and* that the signature itself
    verifies, so a cert can't claim trust just by copying a trusted issuer's
    name."""
    if cert.issuer != ca_cert.subject:
        return False
    try:
        ca_cert.public_key().verify(
            cert.signature,
            cert.tbs_certificate_bytes,
            padding.PKCS1v15(),
            cert.signature_hash_algorithm,
        )
    except InvalidSignature:
        return False
    return True


def _extract_emaid(cert: x509.Certificate) -> str | None:
    """Real ISO 15118 contract certificates carry the EMAID in the subject's
    Common Name."""
    common_names = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    return common_names[0].value if common_names else None


class PlugAndChargeValidator:
    def __init__(
        self,
        trusted_ca_certs_pem: list[str],
        emaid_map: EmaidDriverMap,
        ocsp_checker: OcspChecker | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._trusted_cas = [x509.load_pem_x509_certificate(pem.encode()) for pem in trusted_ca_certs_pem]
        self._emaid_map = emaid_map
        self._ocsp_checker = ocsp_checker
        self._clock = clock

    async def resolve_driver_from_cert(self, cert_pem: str) -> uuid.UUID:
        try:
            cert = x509.load_pem_x509_certificate(cert_pem.encode())
        except ValueError as exc:
            raise PlugAndChargeError("malformed certificate") from exc

        if not any(_signed_by(cert, ca) for ca in self._trusted_cas):
            raise PlugAndChargeError("certificate not signed by any trusted CA")

        now = self._clock()
        if now < cert.not_valid_before_utc or now > cert.not_valid_after_utc:
            raise PlugAndChargeError("certificate is not within its validity period")

        if self._ocsp_checker is not None and await self._ocsp_checker.is_revoked(cert.serial_number):
            raise PlugAndChargeError("certificate has been revoked")

        emaid = _extract_emaid(cert)
        if not emaid:
            raise PlugAndChargeError("certificate missing EMAID in subject common name")

        driver_id = await self._emaid_map.get_driver_id_for_emaid(emaid)
        if driver_id is None:
            raise PlugAndChargeError(f"no driver account mapped for EMAID {emaid}")
        return driver_id

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

import httpx
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.hashes import SHA1
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import NameOID
from cryptography.x509.ocsp import OCSPResponseStatus, load_der_ocsp_response
from cryptography.x509.ocsp import OCSPCertStatus, OCSPRequestBuilder


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
    """A revoked contract certificate is otherwise indistinguishable from a
    valid one — signature and validity-period checks alone would accept it.
    Takes the issuer too (not just a serial number) because a real OCSP
    request is keyed on issuer-name-hash + issuer-key-hash + serial, per
    RFC 6960 — a serial number alone isn't enough to build one."""

    async def is_revoked(self, cert: x509.Certificate, issuer: x509.Certificate) -> bool: ...


class InMemoryOcspChecker:
    """The `app_mode=testing` default — every cert is presumed good unless
    explicitly marked revoked by serial number."""

    def __init__(self) -> None:
        self._revoked: set[int] = set()

    def revoke(self, serial_number: int) -> None:
        self._revoked.add(serial_number)

    async def is_revoked(self, cert: x509.Certificate, issuer: x509.Certificate) -> bool:
        return cert.serial_number in self._revoked


class OcspError(Exception):
    pass


class HttpOcspChecker:
    """Real RFC 6960 OCSP client — the `app_mode=production` implementation,
    pending a live OEM/CA responder URL to point at (no such responder is
    wired up or integration-tested against yet; see `settings.ocsp_responder_url`).

    Fails closed: any transport error, non-200 response, or unparseable/
    unsuccessful OCSP response is treated as "cannot confirm this cert is
    good" and raises rather than silently treating the cert as valid.
    """

    def __init__(
        self,
        responder_url: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._responder_url = responder_url
        self._http_client = http_client

    async def is_revoked(self, cert: x509.Certificate, issuer: x509.Certificate) -> bool:
        request = (
            OCSPRequestBuilder()
            .add_cert(cert, issuer, SHA1())
            .build()
        )
        client = self._http_client or httpx.AsyncClient()

        try:
            response = await client.post(
                self._responder_url,
                content=request.public_bytes(Encoding.DER),
                headers={"Content-Type": "application/ocsp-request"},
            )
        except httpx.HTTPError as exc:
            raise OcspError(f"OCSP responder unreachable: {exc}") from exc

        if response.status_code != 200:
            raise OcspError(f"OCSP responder returned status {response.status_code}")

        try:
            ocsp_response = load_der_ocsp_response(response.content)
        except ValueError as exc:
            raise OcspError("malformed OCSP response") from exc

        if ocsp_response.response_status != OCSPResponseStatus.SUCCESSFUL:
            raise OcspError(f"OCSP responder did not return a successful status: {ocsp_response.response_status}")

        return ocsp_response.certificate_status != OCSPCertStatus.GOOD


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

        issuer_ca = next((ca for ca in self._trusted_cas if _signed_by(cert, ca)), None)
        if issuer_ca is None:
            raise PlugAndChargeError("certificate not signed by any trusted CA")

        now = self._clock()
        if now < cert.not_valid_before_utc or now > cert.not_valid_after_utc:
            raise PlugAndChargeError("certificate is not within its validity period")

        if self._ocsp_checker is not None and await self._ocsp_checker.is_revoked(cert, issuer_ca):
            raise PlugAndChargeError("certificate has been revoked")

        emaid = _extract_emaid(cert)
        if not emaid:
            raise PlugAndChargeError("certificate missing EMAID in subject common name")

        driver_id = await self._emaid_map.get_driver_id_for_emaid(emaid)
        if driver_id is None:
            raise PlugAndChargeError(f"no driver account mapped for EMAID {emaid}")
        return driver_id

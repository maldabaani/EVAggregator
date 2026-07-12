"""Shared X.509 test-cert builders for Plug & Charge tests — not a fixture
module for a real CA, just enough to build a signed leaf cert for a given
private key, mirroring the shape of a real ISO 15118 contract certificate."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.oid import NameOID


def pem(cert: x509.Certificate) -> str:
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def make_ca_cert(private_key, common_name: str = "Test OEM Root CA") -> x509.Certificate:
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.now(timezone.utc)
    return (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(private_key, hashes.SHA256())
    )


def make_leaf_cert(
    issuer_private_key,
    issuer_cert: x509.Certificate,
    leaf_public_key,
    emaid: str | None = "EMAID-ABC123",
    not_before: datetime | None = None,
    not_after: datetime | None = None,
) -> x509.Certificate:
    now = datetime.now(timezone.utc)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, emaid)]) if emaid is not None else x509.Name([])
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer_cert.subject)
        .public_key(leaf_public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before or now - timedelta(minutes=5))
        .not_valid_after(not_after or now + timedelta(days=30))
        .sign(issuer_private_key, hashes.SHA256())
    )

"""Task 6.3 — SSO for enterprise operator portal customers: generic OIDC and
SAML support (no single vendor assumed; each tenant configures its own IdP).

`OIDCProvider` validates an id_token's signature via an injectable key
resolver (JWKS lookup in production, a fixed test key in unit tests) plus
issuer/audience/expiry — this is real signature verification.

`SAMLProvider` is intentionally scoped down: it parses the assertion and
checks issuer/NameID/expiry, but does **not** perform XML-DSig signature
verification, which needs a hardened library (`python3-saml` / `signxml`)
wired to each IdP's certificate. Flagged here rather than silently faked —
do not point this at a real IdP until that's added.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Protocol

import jwt

_SAML_NS = {
    "samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
    "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
}


class SSOError(Exception):
    """Raised for any failed SSO authentication attempt."""


@dataclass(frozen=True)
class SSOIdentity:
    subject_id: str
    email: str | None = None


class SSOProvider(Protocol):
    def authenticate(self, credential: str) -> SSOIdentity: ...


class OIDCProvider:
    def __init__(
        self,
        issuer: str,
        audience: str,
        key_resolver: Callable[[str], str],
        algorithm: str = "RS256",
    ) -> None:
        self._issuer = issuer
        self._audience = audience
        self._key_resolver = key_resolver
        self._algorithm = algorithm

    def authenticate(self, id_token: str) -> SSOIdentity:
        try:
            unverified_header = jwt.get_unverified_header(id_token)
            key = self._key_resolver(unverified_header.get("kid", ""))
            claims = jwt.decode(
                id_token,
                key,
                algorithms=[self._algorithm],
                audience=self._audience,
                issuer=self._issuer,
            )
        except jwt.PyJWTError as exc:
            raise SSOError(str(exc)) from exc

        subject = claims.get("sub")
        if not subject:
            raise SSOError("id_token missing sub claim")
        return SSOIdentity(subject_id=subject, email=claims.get("email"))


class SAMLProvider:
    def __init__(self, issuer: str) -> None:
        self._issuer = issuer

    def authenticate(self, saml_response_xml: str) -> SSOIdentity:
        try:
            root = ET.fromstring(saml_response_xml)
        except ET.ParseError as exc:
            raise SSOError(f"malformed SAML response: {exc}") from exc

        assertion = root.find("saml:Assertion", _SAML_NS)
        if assertion is None:
            raise SSOError("no assertion present in SAML response")

        issuer_el = assertion.find("saml:Issuer", _SAML_NS)
        if issuer_el is None or issuer_el.text != self._issuer:
            raise SSOError("unexpected SAML issuer")

        name_id_el = assertion.find("saml:Subject/saml:NameID", _SAML_NS)
        if name_id_el is None or not name_id_el.text:
            raise SSOError("SAML assertion missing NameID")

        conditions_el = assertion.find("saml:Conditions", _SAML_NS)
        if conditions_el is not None:
            not_on_or_after = conditions_el.get("NotOnOrAfter")
            if not_on_or_after:
                expiry = datetime.fromisoformat(not_on_or_after.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) >= expiry:
                    raise SSOError("SAML assertion expired")

        return SSOIdentity(subject_id=name_id_el.text)

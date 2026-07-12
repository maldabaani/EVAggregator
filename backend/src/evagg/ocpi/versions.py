"""Task 1.1 — OCPI `/versions` and `/{version}/credentials` handshake.

2.1.1 is listed as read-only (Locations + Tariffs GET only — see
`evagg.ocpi.v211_shim`); 2.2.1 is primary; 2.3.0 runs alongside for forward
compatibility.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from evagg.ocpi.errors import OcpiErrorCode, OcpiError
from evagg.ocpi.partner_store import PartnerRegistry

SUPPORTED_VERSIONS = ("2.1.1", "2.2.1", "2.3.0")
READ_ONLY_VERSIONS = frozenset({"2.1.1"})


@dataclass(frozen=True)
class VersionEndpointInfo:
    version: str
    url: str


def build_versions_response(base_url: str) -> dict:
    return {
        "status_code": int(OcpiErrorCode.SUCCESS),
        "status_message": "Success",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": [{"version": version, "url": f"{base_url}/{version}"} for version in SUPPORTED_VERSIONS],
    }


async def negotiate_credentials(
    registry: PartnerRegistry, token_a: str, requested_version: str
) -> dict:
    """Handles the `/{version}/credentials` handshake: validates the partner's
    token_a, rejects an unsupported version, issues a fresh token_c, and
    persists the negotiated version — all before any Location/Session/CDR
    endpoint becomes reachable for that partner.
    """
    if requested_version not in SUPPORTED_VERSIONS:
        raise OcpiError(OcpiErrorCode.UNSUPPORTED_VERSION, f"version {requested_version} is not supported")

    partner = await registry.find_by_token_a(token_a)
    if partner is None:
        raise OcpiError(OcpiErrorCode.UNKNOWN_TOKEN, "unknown partner token")

    token_c = secrets.token_urlsafe(24)
    await registry.set_negotiated_version(partner.id, requested_version, token_c)

    return {
        "status_code": int(OcpiErrorCode.SUCCESS),
        "status_message": "Success",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {"token": token_c, "url": f"/ocpi/{requested_version}/versions", "roles": []},
    }


async def authenticate_partner(registry: PartnerRegistry, bearer_token: str) -> uuid.UUID:
    """Returns the authenticated partner's id, or raises 2004 unknown_token —
    the shared auth seam for every protected OCPI route."""
    partner = await registry.find_by_token_c(bearer_token)
    if partner is None:
        raise OcpiError(OcpiErrorCode.UNKNOWN_TOKEN, "unknown or unrecognized partner token")
    return partner.id

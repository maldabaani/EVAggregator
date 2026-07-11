"""Signs the trusted `X-Tenant-Id` header the gateway forwards to internal
services, so a client can never spoof tenant context by setting the header
directly on a request that bypasses the gateway (Task 6.3's acceptance
criteria). Internal services verify the signature before trusting the header
at all — see `evagg.gateway.middleware.GatewaySignatureMiddleware`.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid

from evagg.core.config import settings

SIGNATURE_HEADER = "x-gateway-signature"


def sign_tenant_id(tenant_id: uuid.UUID) -> str:
    return hmac.new(
        settings.gateway_trust_secret.encode("utf-8"), str(tenant_id).encode("utf-8"), hashlib.sha256
    ).hexdigest()


def verify_tenant_signature(tenant_id: uuid.UUID, signature: str) -> bool:
    expected = sign_tenant_id(tenant_id)
    return hmac.compare_digest(expected, signature)

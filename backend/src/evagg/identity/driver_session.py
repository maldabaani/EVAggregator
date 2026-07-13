"""FastAPI dependencies extracting & validating the authenticated driver
from a Bearer access token issued by `evagg.identity.driver_auth_router`,
so driver-scoped routes (vehicles, and the session-start forwarder) derive
`driver_id`/`tenant_id` from a verified token rather than trusting a
client-supplied value — the latter would let any caller read or modify
another driver's data, or claim a tenant they don't belong to, just by
passing different values.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException

from evagg.gateway.jwt_tokens import TokenError, decode_access_token


@dataclass(frozen=True)
class DriverIdentity:
    driver_id: uuid.UUID
    tenant_id: uuid.UUID


async def require_driver_identity(authorization: str | None = Header(default=None)) -> DriverIdentity:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ")
    try:
        payload = decode_access_token(token)
    except TokenError:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    try:
        return DriverIdentity(driver_id=uuid.UUID(payload["sub"]), tenant_id=uuid.UUID(payload["tenant_id"]))
    except (KeyError, ValueError):
        raise HTTPException(status_code=401, detail="malformed token subject")


async def require_driver_id(identity: DriverIdentity = Depends(require_driver_identity)) -> uuid.UUID:
    return identity.driver_id

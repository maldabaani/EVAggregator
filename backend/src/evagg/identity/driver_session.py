"""FastAPI dependency extracting & validating the authenticated driver from
a Bearer access token issued by `evagg.identity.driver_auth_router`, so
driver-scoped routes (vehicles, and future wallet/session endpoints) derive
`driver_id` from a verified token rather than trusting a client-supplied
value — the latter would let any caller read or modify another driver's
data just by passing a different id.
"""

from __future__ import annotations

import uuid

from fastapi import Header, HTTPException

from evagg.gateway.jwt_tokens import TokenError, decode_access_token


async def require_driver_id(authorization: str | None = Header(default=None)) -> uuid.UUID:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ")
    try:
        payload = decode_access_token(token)
    except TokenError:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=401, detail="malformed token subject")

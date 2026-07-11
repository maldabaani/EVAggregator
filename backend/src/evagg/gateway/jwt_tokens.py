"""Access token issuance/validation for Task 6.3.

Access tokens are short-lived JWTs (~15 min per engineering standards) carrying
`sub` (subject id), `tenant_id`, and a `jti` for traceability. Refresh tokens
are opaque (not JWTs) and live in `RefreshTokenStore` (see refresh_store.py) so
rotation/revocation doesn't require a token blocklist.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt

from evagg.core.config import settings


class TokenError(Exception):
    """Raised for any invalid/expired access token — callers should map this
    to a 401, never leak the underlying jwt library exception type."""


def create_access_token(subject: str, tenant_id: uuid.UUID, ttl_seconds: int | None = None) -> str:
    now = datetime.now(timezone.utc)
    ttl = ttl_seconds if ttl_seconds is not None else settings.jwt_access_token_ttl_seconds
    payload = {
        "sub": subject,
        "tenant_id": str(tenant_id),
        "iat": now,
        "exp": now + timedelta(seconds=ttl),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_signing_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_signing_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc

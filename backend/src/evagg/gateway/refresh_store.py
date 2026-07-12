"""Refresh token rotation with reuse detection (Task 6.3).

Refresh tokens are opaque, single-use, and grouped into a "family" created at
login. Rotating a token issues a new one and retires the old; presenting an
already-retired token again (a signal the token was stolen and replayed)
revokes the *entire* family rather than just failing one request.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from typing import Protocol


class RefreshTokenError(Exception):
    """Raised for unknown, revoked, or reused refresh tokens."""


@dataclass(frozen=True)
class RefreshToken:
    token: str
    family_id: str
    subject: str
    tenant_id: uuid.UUID


class RefreshTokenStore(Protocol):
    async def issue(self, subject: str, tenant_id: uuid.UUID) -> RefreshToken: ...

    async def rotate(self, token: str) -> RefreshToken: ...

    async def revoke_family(self, family_id: str) -> None: ...


class InMemoryRefreshTokenStore:
    """Reference implementation used by tests and local dev. Production wires
    the same interface to Redis so rotation state survives gateway restarts."""

    def __init__(self) -> None:
        self._tokens: dict[str, RefreshToken] = {}
        self._current_by_family: dict[str, str] = {}
        self._revoked_families: set[str] = set()

    async def issue(self, subject: str, tenant_id: uuid.UUID) -> RefreshToken:
        family_id = str(uuid.uuid4())
        token_value = secrets.token_urlsafe(32)
        rt = RefreshToken(token=token_value, family_id=family_id, subject=subject, tenant_id=tenant_id)
        self._tokens[token_value] = rt
        self._current_by_family[family_id] = token_value
        return rt

    async def rotate(self, token: str) -> RefreshToken:
        existing = self._tokens.get(token)
        if existing is None:
            raise RefreshTokenError("unknown refresh token")
        if existing.family_id in self._revoked_families:
            raise RefreshTokenError("refresh token family revoked")
        if self._current_by_family.get(existing.family_id) != token:
            # This token was already rotated away — someone is replaying a
            # retired token. Treat the whole family as compromised.
            self._revoked_families.add(existing.family_id)
            raise RefreshTokenError("refresh token reuse detected; family revoked")

        new_token_value = secrets.token_urlsafe(32)
        new_rt = RefreshToken(
            token=new_token_value,
            family_id=existing.family_id,
            subject=existing.subject,
            tenant_id=existing.tenant_id,
        )
        self._tokens[new_token_value] = new_rt
        self._current_by_family[existing.family_id] = new_token_value
        return new_rt

    async def revoke_family(self, family_id: str) -> None:
        self._revoked_families.add(family_id)

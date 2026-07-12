"""Task 1.1 — partner lookup seam used by version negotiation and by every
protected OCPI route to authenticate the caller's bearer token. Backed by the
`ocpi_partner` table (Task 6.1) in production; in-memory for tests.

Task 1.3 extends this with `rotate_token_a` (portal credential rotation) and
`list_all` (portal partner list).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol


@dataclass
class Partner:
    id: uuid.UUID
    tenant_id: uuid.UUID
    party_id: str
    country_code: str
    token_a: str
    token_c: str | None
    negotiated_version: str | None
    status: str  # 'pending' | 'connected' | 'suspended'
    last_handshake_at: datetime | None = None


class PartnerRegistry(Protocol):
    async def find_by_token_a(self, token: str) -> Partner | None: ...

    async def find_by_token_c(self, token: str) -> Partner | None: ...

    async def set_negotiated_version(self, partner_id: uuid.UUID, version: str, token_c: str) -> None: ...

    async def rotate_token_a(self, partner_id: uuid.UUID, new_token_a: str) -> None: ...

    async def list_all(self) -> list[Partner]: ...


class InMemoryPartnerRegistry:
    def __init__(self, partners: list[Partner] | None = None) -> None:
        self._partners: dict[uuid.UUID, Partner] = {p.id: p for p in (partners or [])}

    def add(self, partner: Partner) -> None:
        self._partners[partner.id] = partner

    async def find_by_token_a(self, token: str) -> Partner | None:
        return next((p for p in self._partners.values() if p.token_a == token), None)

    async def find_by_token_c(self, token: str) -> Partner | None:
        return next((p for p in self._partners.values() if p.token_c == token), None)

    async def set_negotiated_version(self, partner_id: uuid.UUID, version: str, token_c: str) -> None:
        partner = self._partners[partner_id]
        partner.negotiated_version = version
        partner.token_c = token_c
        partner.status = "connected"
        partner.last_handshake_at = datetime.now(timezone.utc)

    async def rotate_token_a(self, partner_id: uuid.UUID, new_token_a: str) -> None:
        self._partners[partner_id].token_a = new_token_a

    async def list_all(self) -> list[Partner]:
        return list(self._partners.values())

"""Task 1.1 — partner lookup seam used by version negotiation and by every
protected OCPI route to authenticate the caller's bearer token. Backed by the
`ocpi_partner` table (Task 6.1) in production; in-memory for tests.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
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


class PartnerRegistry(Protocol):
    async def find_by_token_a(self, token: str) -> Partner | None: ...

    async def find_by_token_c(self, token: str) -> Partner | None: ...

    async def set_negotiated_version(self, partner_id: uuid.UUID, version: str, token_c: str) -> None: ...


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

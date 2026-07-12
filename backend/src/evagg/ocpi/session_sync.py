"""Task 1.2 — as CPO, push a `PATCH /sessions/{id}` to the partner on every
`MeterValues` event from Epic 2's event bus, so partner-visible session kWh
stays live without the partner polling.
"""

from __future__ import annotations

import uuid
from typing import Protocol

import httpx


class SessionPushClient(Protocol):
    async def push_session_patch(self, partner_id: uuid.UUID, session_id: str, kwh: float) -> None: ...


class InMemorySessionPushClient:
    """The `app_mode=testing` default — records pushes for assertions
    instead of calling out to a real partner network."""

    def __init__(self) -> None:
        self.patches: list[tuple[uuid.UUID, str, float]] = []

    async def push_session_patch(self, partner_id: uuid.UUID, session_id: str, kwh: float) -> None:
        self.patches.append((partner_id, session_id, kwh))


class SessionPushError(Exception):
    pass


class HttpSessionPushClient:
    """Real OCPI `PATCH /sessions/{session_id}` push — the
    `app_mode=production` implementation, pending real per-partner base URLs
    and tokens (see `HttpPartnerPushClient`'s docstring for the same caveat:
    one shared endpoint here, not a per-partner lookup, until that store
    exists)."""

    def __init__(self, base_url: str, token: str, http_client: httpx.AsyncClient | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._http_client = http_client

    async def push_session_patch(self, partner_id: uuid.UUID, session_id: str, kwh: float) -> None:
        client = self._http_client or httpx.AsyncClient()
        try:
            response = await client.patch(
                f"{self._base_url}/sessions/{session_id}",
                json={"kwh": kwh},
                headers={"Authorization": f"Token {self._token}"},
            )
        except httpx.HTTPError as exc:
            raise SessionPushError(f"partner {partner_id} unreachable: {exc}") from exc

        if response.status_code >= 400:
            raise SessionPushError(f"partner {partner_id} rejected session push (status {response.status_code})")


class SessionSyncService:
    def __init__(self, push_client: SessionPushClient) -> None:
        self._push_client = push_client

    async def handle_meter_values(self, partner_id: uuid.UUID, session_id: str, kwh: float) -> None:
        await self._push_client.push_session_patch(partner_id, session_id, kwh)

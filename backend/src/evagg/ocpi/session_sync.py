"""Task 1.2 — as CPO, push a `PATCH /sessions/{id}` to the partner on every
`MeterValues` event from Epic 2's event bus, so partner-visible session kWh
stays live without the partner polling.
"""

from __future__ import annotations

import uuid
from typing import Protocol


class SessionPushClient(Protocol):
    async def push_session_patch(self, partner_id: uuid.UUID, session_id: str, kwh: float) -> None: ...


class InMemorySessionPushClient:
    def __init__(self) -> None:
        self.patches: list[tuple[uuid.UUID, str, float]] = []

    async def push_session_patch(self, partner_id: uuid.UUID, session_id: str, kwh: float) -> None:
        self.patches.append((partner_id, session_id, kwh))


class SessionSyncService:
    def __init__(self, push_client: SessionPushClient) -> None:
        self._push_client = push_client

    async def handle_meter_values(self, partner_id: uuid.UUID, session_id: str, kwh: float) -> None:
        await self._push_client.push_session_patch(partner_id, session_id, kwh)

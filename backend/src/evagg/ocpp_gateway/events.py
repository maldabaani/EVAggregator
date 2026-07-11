"""Outbound NATS event publishing for the gateway (real JetStream wiring is
Task 2.4 — this is the interface the connection manager depends on, so it can
be tested without a live NATS server).
"""

from __future__ import annotations

import uuid
from typing import Protocol


class EventPublisher(Protocol):
    async def publish_disconnected(self, tenant_id: uuid.UUID, charger_id: str) -> None: ...


class InMemoryEventPublisher:
    def __init__(self) -> None:
        self.published: list[tuple[uuid.UUID, str]] = []

    async def publish_disconnected(self, tenant_id: uuid.UUID, charger_id: str) -> None:
        self.published.append((tenant_id, charger_id))

"""Outbound NATS event publishing for the gateway (real JetStream wiring is
Task 2.4 — this is the interface the connection manager and message handlers
depend on, so both can be tested without a live NATS server).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Protocol


class EventPublisher(Protocol):
    async def publish_disconnected(self, tenant_id: uuid.UUID, charger_id: str) -> None: ...

    async def publish_status_notification(
        self, tenant_id: uuid.UUID, charger_id: str, connector_id: int, status: str, error_code: str | None
    ) -> None: ...

    async def publish_stop_transaction(
        self, tenant_id: uuid.UUID, charger_id: str, transaction_id: uuid.UUID
    ) -> None: ...

    async def publish_ocpp_event(
        self, tenant_id: uuid.UUID, charger_id: str, event_type: str, payload: dict
    ) -> None:
        """One generic subject (`ocpp.{tenant}.{charger}.{event_type}`) for
        the lower-volume, non-transactional notifications — DataTransfer,
        FirmwareStatusNotification, DiagnosticsStatusNotification,
        SecurityEventNotification, LogStatusNotification — rather than a
        dedicated method (and dedicated NATS subject helper) per action.
        None of these drive billing or session state the way status/stop
        transaction events do, so one shared, loggable/auditable stream is
        enough."""
        ...


@dataclass
class InMemoryEventPublisher:
    published: list[tuple[uuid.UUID, str]] = field(default_factory=list)
    status_notifications: list[tuple[uuid.UUID, str, int, str, str | None]] = field(default_factory=list)
    stop_transactions: list[tuple[uuid.UUID, str, uuid.UUID]] = field(default_factory=list)
    ocpp_events: list[tuple[uuid.UUID, str, str, dict]] = field(default_factory=list)

    async def publish_disconnected(self, tenant_id: uuid.UUID, charger_id: str) -> None:
        self.published.append((tenant_id, charger_id))

    async def publish_status_notification(
        self, tenant_id: uuid.UUID, charger_id: str, connector_id: int, status: str, error_code: str | None
    ) -> None:
        self.status_notifications.append((tenant_id, charger_id, connector_id, status, error_code))

    async def publish_stop_transaction(
        self, tenant_id: uuid.UUID, charger_id: str, transaction_id: uuid.UUID
    ) -> None:
        self.stop_transactions.append((tenant_id, charger_id, transaction_id))

    async def publish_ocpp_event(
        self, tenant_id: uuid.UUID, charger_id: str, event_type: str, payload: dict
    ) -> None:
        self.ocpp_events.append((tenant_id, charger_id, event_type, payload))

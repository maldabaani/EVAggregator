"""Concrete `EventPublisher` (Tasks 2.1/2.2's dependency) backed by any
`EventBus` implementation — the in-memory one for tests, `NatsEventBus` in
production. This is the piece that turns the abstract "publish a disconnect/
status/stop-transaction event" calls those tasks already make into real
`ocpp.{tenant}.{charger}.{event_type}` subject publishes.
"""

from __future__ import annotations

import uuid

from evagg.ocpp_gateway.event_bus import EventBus, event_subject


class BusEventPublisher:
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    async def publish_disconnected(self, tenant_id: uuid.UUID, charger_id: str) -> None:
        await self._bus.publish(event_subject(tenant_id, charger_id, "disconnected"), {"charger_id": charger_id})

    async def publish_status_notification(
        self, tenant_id: uuid.UUID, charger_id: str, connector_id: int, status: str, error_code: str | None
    ) -> None:
        await self._bus.publish(
            event_subject(tenant_id, charger_id, "status_notification"),
            {"charger_id": charger_id, "connector_id": connector_id, "status": status, "error_code": error_code},
        )

    async def publish_stop_transaction(self, tenant_id: uuid.UUID, charger_id: str, transaction_id: uuid.UUID) -> None:
        await self._bus.publish(
            event_subject(tenant_id, charger_id, "stop_transaction"),
            {"charger_id": charger_id, "transaction_id": str(transaction_id)},
        )

    async def publish_ocpp_event(
        self, tenant_id: uuid.UUID, charger_id: str, event_type: str, payload: dict
    ) -> None:
        await self._bus.publish(
            event_subject(tenant_id, charger_id, event_type),
            {"charger_id": charger_id, **payload},
        )

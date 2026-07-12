"""Task 2.2 — Core OCPP inbound message handling.

`handle_frame` is the single dispatch entrypoint the LLD calls for
(action -> handler map); each handler is also directly callable with typed
arguments, which is what the unit tests below exercise — `handle_frame` is a
thin adapter over the same methods, not a second implementation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from typing import TYPE_CHECKING

from evagg.ocpp_gateway.authorize import AuthStatus, Authorizer
from evagg.ocpp_gateway.connectors import ConnectorStore
from evagg.ocpp_gateway.events import EventPublisher
from evagg.ocpp_gateway.meter_values import MeterReading, MeterValueBuffer
from evagg.ocpp_gateway.registration import ChargerRegistry
from evagg.ocpp_gateway.transactions import ActiveTransaction, StopResult, TransactionRepository

if TYPE_CHECKING:
    from evagg.ocpp_gateway.commands import FirmwareUpdateStore

_BOOT_STATUS_MAP = {"pending": "Pending", "accepted": "Accepted", "rejected": "Rejected"}


@dataclass
class BootNotificationResponse:
    status: str
    interval_seconds: int


@dataclass
class StartTransactionResponse:
    transaction_id: uuid.UUID
    id_tag_status: str


@dataclass
class StopTransactionResponse:
    id_tag_status: str = "Accepted"


class OcppMessageHandlers:
    def __init__(
        self,
        charger_registry: ChargerRegistry,
        connector_store: ConnectorStore,
        authorizer: Authorizer,
        transaction_repository: TransactionRepository,
        meter_value_buffer: MeterValueBuffer,
        events: EventPublisher,
        default_heartbeat_interval_seconds: int = 300,
        firmware_update_store: "FirmwareUpdateStore | None" = None,
    ) -> None:
        self._charger_registry = charger_registry
        self._connector_store = connector_store
        self._authorizer = authorizer
        self._transactions = transaction_repository
        self._meter_values = meter_value_buffer
        self._events = events
        self._default_heartbeat_interval_seconds = default_heartbeat_interval_seconds
        # Optional: FirmwareStatusNotification still publishes an OCPP event
        # without it, it just can't also update Task 2.3's FirmwareUpdateStore
        # (kept optional so Task 2.2's tests don't need Task 2.3's module).
        self._firmware_update_store = firmware_update_store

    async def handle_boot_notification(
        self,
        charger_id: str,
        tenant_id: uuid.UUID,
        vendor: str | None,
        model: str | None,
        firmware_version: str | None,
    ) -> BootNotificationResponse:
        result = await self._charger_registry.upsert_on_boot(charger_id, tenant_id, vendor, model, firmware_version)
        return BootNotificationResponse(
            status=_BOOT_STATUS_MAP[result.status],
            interval_seconds=self._default_heartbeat_interval_seconds,
        )

    async def handle_status_notification(
        self, charger_id: str, tenant_id: uuid.UUID, connector_id: int, status: str, error_code: str | None
    ) -> None:
        await self._connector_store.update_status(charger_id, connector_id, status, error_code)
        await self._events.publish_status_notification(tenant_id, charger_id, connector_id, status, error_code)

    async def handle_authorize(self, id_tag: str) -> AuthStatus:
        return await self._authorizer.authorize(id_tag)

    async def handle_start_transaction(
        self,
        charger_id: str,
        tenant_id: uuid.UUID,
        connector_id: int,
        id_tag: str,
        meter_start: int,
        start_timestamp: datetime,
    ) -> StartTransactionResponse:
        auth_status = await self._authorizer.authorize(id_tag)
        if auth_status != AuthStatus.ACCEPTED:
            return StartTransactionResponse(transaction_id=uuid.UUID(int=0), id_tag_status=auth_status.value)

        txn: ActiveTransaction = await self._transactions.start_transaction(
            charger_id, tenant_id, connector_id, id_tag, meter_start, start_timestamp
        )
        return StartTransactionResponse(transaction_id=txn.id, id_tag_status=AuthStatus.ACCEPTED.value)

    async def handle_stop_transaction(
        self,
        transaction_id: uuid.UUID,
        meter_stop: int,
        stop_timestamp: datetime,
        reason: str | None = None,
    ) -> StopTransactionResponse:
        # Flush any buffered readings for this session before it closes out —
        # otherwise trailing MeterValues could sit unwritten indefinitely.
        await self._meter_values.flush()

        result: StopResult = await self._transactions.stop_transaction(transaction_id, meter_stop, stop_timestamp, reason)
        if not result.already_stopped:
            await self._events.publish_stop_transaction(result.tenant_id, result.charger_id, transaction_id)
        return StopTransactionResponse()

    async def handle_meter_values(
        self,
        tenant_id: uuid.UUID,
        transaction_id: uuid.UUID,
        charger_id: str,
        ts: datetime,
        readings: list[tuple[str, float, str]],
    ) -> None:
        """`readings` is a list of (measurand, value, unit) tuples — one
        MeterValues frame typically carries several sampled values."""
        for measurand, value, unit in readings:
            await self._meter_values.add(
                MeterReading(
                    tenant_id=tenant_id,
                    transaction_id=transaction_id,
                    charger_id=charger_id,
                    ts=ts,
                    measurand=measurand,
                    value=value,
                    unit=unit,
                )
            )

    async def handle_data_transfer(
        self, charger_id: str, tenant_id: uuid.UUID, vendor_id: str, message_id: str | None, data: str | None
    ) -> dict:
        """No vendor-specific extension is implemented (none is needed yet)
        — this is the generic pass-through/extension point the spec
        requires every CSMS to at least acknowledge, not a specific vendor
        integration. Always Accepted; publishes the raw payload so a real
        vendor handler can be added later without changing this shape."""
        await self._events.publish_ocpp_event(
            tenant_id, charger_id, "data_transfer", {"vendor_id": vendor_id, "message_id": message_id, "data": data}
        )
        return {"status": "Accepted"}

    async def handle_firmware_status_notification(self, charger_id: str, tenant_id: uuid.UUID, status: str) -> None:
        await self._events.publish_ocpp_event(tenant_id, charger_id, "firmware_status", {"status": status})
        if self._firmware_update_store is not None:
            record = await self._firmware_update_store.get_latest_for_charger(charger_id)
            if record is not None:
                await self._firmware_update_store.update_status(charger_id, record.version, status)

    async def handle_diagnostics_status_notification(
        self, charger_id: str, tenant_id: uuid.UUID, status: str
    ) -> None:
        await self._events.publish_ocpp_event(tenant_id, charger_id, "diagnostics_status", {"status": status})

    async def handle_security_event_notification(
        self, charger_id: str, tenant_id: uuid.UUID, event_type: str, timestamp: str, tech_info: str | None
    ) -> None:
        await self._events.publish_ocpp_event(
            tenant_id, charger_id, "security_event", {"type": event_type, "timestamp": timestamp, "tech_info": tech_info}
        )

    async def handle_log_status_notification(
        self, charger_id: str, tenant_id: uuid.UUID, status: str, request_id: int | None
    ) -> None:
        await self._events.publish_ocpp_event(
            tenant_id, charger_id, "log_status", {"status": status, "request_id": request_id}
        )

    async def handle_frame(self, charger_id: str, tenant_id: uuid.UUID, action: str, payload: dict) -> dict:
        if action == "BootNotification":
            response = await self.handle_boot_notification(
                charger_id, tenant_id, payload.get("vendor"), payload.get("model"), payload.get("firmware_version")
            )
            return {"status": response.status, "interval": response.interval_seconds}

        if action == "StatusNotification":
            await self.handle_status_notification(
                charger_id, tenant_id, payload["connector_id"], payload["status"], payload.get("error_code")
            )
            return {}

        if action == "Authorize":
            status = await self.handle_authorize(payload["id_tag"])
            return {"id_tag_status": status.value}

        if action == "StartTransaction":
            response = await self.handle_start_transaction(
                charger_id,
                tenant_id,
                payload["connector_id"],
                payload["id_tag"],
                payload["meter_start"],
                payload["start_timestamp"],
            )
            return {"transaction_id": str(response.transaction_id), "id_tag_status": response.id_tag_status}

        if action == "StopTransaction":
            response = await self.handle_stop_transaction(
                uuid.UUID(payload["transaction_id"]),
                payload["meter_stop"],
                payload["stop_timestamp"],
                payload.get("reason"),
            )
            return {"id_tag_status": response.id_tag_status}

        if action == "MeterValues":
            await self.handle_meter_values(
                tenant_id,
                uuid.UUID(payload["transaction_id"]),
                charger_id,
                payload["ts"],
                payload["readings"],
            )
            return {}

        if action == "DataTransfer":
            return await self.handle_data_transfer(
                charger_id, tenant_id, payload["vendor_id"], payload.get("message_id"), payload.get("data")
            )

        if action == "FirmwareStatusNotification":
            await self.handle_firmware_status_notification(charger_id, tenant_id, payload["status"])
            return {}

        if action == "DiagnosticsStatusNotification":
            await self.handle_diagnostics_status_notification(charger_id, tenant_id, payload["status"])
            return {}

        if action == "SecurityEventNotification":
            await self.handle_security_event_notification(
                charger_id, tenant_id, payload["type"], payload["timestamp"], payload.get("tech_info")
            )
            return {}

        if action == "LogStatusNotification":
            await self.handle_log_status_notification(charger_id, tenant_id, payload["status"], payload.get("request_id"))
            return {}

        raise ValueError(f"unsupported OCPP action: {action}")

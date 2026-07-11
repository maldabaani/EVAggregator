"""Task 2.3 — OCPP Outbound Remote Commands Engine.

`RemoteCommandService.send_command` is the single entrypoint: look up the
charger's connected gateway node via the presence registry (Task 2.1), fail
fast if it's offline, otherwise dispatch through `CommandTransport` (real
implementation is NATS request-reply over `ocpp.cmd.{node_id}.{charger_id}`,
wired in Task 2.4) with a bounded timeout, and record the outcome in the
command log for correlation/auditing.

`CommandTransport` owns the actual timeout wait (a real NATS request has a
timeout parameter); this module's tests use `FakeCommandTransport`, which
returns a pre-configured outcome immediately rather than sleeping — a unit
test should never take 30 real seconds to prove a timeout is handled.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol

from evagg.ocpp_gateway.presence import PresenceRegistry


class CommandStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"


class ChargerOfflineError(Exception):
    pass


class ChargingProfileExceedsCapacityError(Exception):
    pass


# --- Command log -------------------------------------------------------


@dataclass
class CommandLogRecord:
    id: uuid.UUID
    charger_id: str
    tenant_id: uuid.UUID
    type: str
    status: CommandStatus
    requested_at: datetime
    responded_at: datetime | None = None
    result: dict | None = None


class CommandLogStore(Protocol):
    async def create(
        self, command_id: uuid.UUID, charger_id: str, tenant_id: uuid.UUID, command_type: str, requested_at: datetime
    ) -> CommandLogRecord: ...

    async def mark_responded(self, command_id: uuid.UUID, status: CommandStatus, result: dict | None) -> None: ...

    async def get(self, command_id: uuid.UUID) -> CommandLogRecord | None: ...


class InMemoryCommandLogStore:
    def __init__(self) -> None:
        self._records: dict[uuid.UUID, CommandLogRecord] = {}

    async def create(
        self, command_id: uuid.UUID, charger_id: str, tenant_id: uuid.UUID, command_type: str, requested_at: datetime
    ) -> CommandLogRecord:
        record = CommandLogRecord(
            id=command_id,
            charger_id=charger_id,
            tenant_id=tenant_id,
            type=command_type,
            status=CommandStatus.PENDING,
            requested_at=requested_at,
        )
        self._records[command_id] = record
        return record

    async def mark_responded(self, command_id: uuid.UUID, status: CommandStatus, result: dict | None) -> None:
        record = self._records[command_id]
        record.status = status
        record.responded_at = datetime.now(timezone.utc)
        record.result = result

    async def get(self, command_id: uuid.UUID) -> CommandLogRecord | None:
        return self._records.get(command_id)


# --- Transport (NATS request-reply, real wiring in Task 2.4) -----------


@dataclass
class CommandOutcome:
    status: CommandStatus
    result: dict | None = None


class CommandTransport(Protocol):
    async def send(
        self,
        node_id: str,
        charger_id: str,
        command_id: uuid.UUID,
        command_type: str,
        payload: dict,
        timeout_seconds: float,
    ) -> CommandOutcome: ...


class FakeCommandTransport:
    """Test double. Records every call; returns a pre-configured outcome per
    charger (default ACCEPTED) instead of performing real request/reply or
    waiting out the timeout window."""

    def __init__(self, default_outcome: CommandOutcome | None = None) -> None:
        self.calls: list[tuple[str, str, uuid.UUID, str, dict, float]] = []
        self._outcomes: dict[str, CommandOutcome] = {}
        self._default_outcome = default_outcome or CommandOutcome(CommandStatus.ACCEPTED, {})

    def set_outcome(self, charger_id: str, outcome: CommandOutcome) -> None:
        self._outcomes[charger_id] = outcome

    async def send(
        self,
        node_id: str,
        charger_id: str,
        command_id: uuid.UUID,
        command_type: str,
        payload: dict,
        timeout_seconds: float,
    ) -> CommandOutcome:
        self.calls.append((node_id, charger_id, command_id, command_type, payload, timeout_seconds))
        return self._outcomes.get(charger_id, self._default_outcome)


# --- Charging profile capacity validation -------------------------------


class ConnectorCapacityProvider(Protocol):
    async def get_max_power_watts(self, charger_id: str, connector_id: int) -> int | None: ...


class InMemoryConnectorCapacityProvider:
    def __init__(self, capacities: dict[tuple[str, int], int] | None = None) -> None:
        self._capacities: dict[tuple[str, int], int] = dict(capacities or {})

    def set_capacity(self, charger_id: str, connector_id: int, max_power_watts: int) -> None:
        self._capacities[(charger_id, connector_id)] = max_power_watts

    async def get_max_power_watts(self, charger_id: str, connector_id: int) -> int | None:
        return self._capacities.get((charger_id, connector_id))


# --- Firmware orchestration ---------------------------------------------


@dataclass
class FirmwareUpdateRecord:
    charger_id: str
    tenant_id: uuid.UUID
    version: str
    status: str  # 'pending' | 'downloading' | 'installing' | 'installed' | 'failed'


class FirmwareUpdateStore(Protocol):
    async def start_update(self, charger_id: str, tenant_id: uuid.UUID, version: str) -> FirmwareUpdateRecord: ...

    async def update_status(self, charger_id: str, version: str, status: str) -> FirmwareUpdateRecord: ...

    async def get(self, charger_id: str, version: str) -> FirmwareUpdateRecord | None: ...


class InMemoryFirmwareUpdateStore:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str], FirmwareUpdateRecord] = {}

    async def start_update(self, charger_id: str, tenant_id: uuid.UUID, version: str) -> FirmwareUpdateRecord:
        record = FirmwareUpdateRecord(charger_id=charger_id, tenant_id=tenant_id, version=version, status="pending")
        self._records[(charger_id, version)] = record
        return record

    async def update_status(self, charger_id: str, version: str, status: str) -> FirmwareUpdateRecord:
        record = self._records.get((charger_id, version))
        if record is None:
            raise ValueError(f"unknown firmware update: {charger_id}@{version}")
        record.status = status
        return record

    async def get(self, charger_id: str, version: str) -> FirmwareUpdateRecord | None:
        return self._records.get((charger_id, version))


# --- The service ---------------------------------------------------------


@dataclass
class CommandResult:
    command_id: uuid.UUID
    status: CommandStatus
    result: dict | None = None


class RemoteCommandService:
    def __init__(
        self,
        presence: PresenceRegistry,
        command_log: CommandLogStore,
        transport: CommandTransport,
        firmware_store: FirmwareUpdateStore,
        default_timeout_seconds: float = 30.0,
    ) -> None:
        self._presence = presence
        self._command_log = command_log
        self._transport = transport
        self._firmware_store = firmware_store
        self._default_timeout_seconds = default_timeout_seconds

    async def send_command(
        self,
        charger_id: str,
        tenant_id: uuid.UUID,
        command_type: str,
        payload: dict,
        timeout_seconds: float | None = None,
    ) -> CommandResult:
        command_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        state = await self._presence.get(charger_id)

        if state is None or state.status != "online":
            await self._command_log.create(command_id, charger_id, tenant_id, command_type, now)
            await self._command_log.mark_responded(command_id, CommandStatus.REJECTED, {"reason": "charger offline"})
            raise ChargerOfflineError(f"charger {charger_id} is offline")

        await self._command_log.create(command_id, charger_id, tenant_id, command_type, now)
        outcome = await self._transport.send(
            node_id=state.node_id,
            charger_id=charger_id,
            command_id=command_id,
            command_type=command_type,
            payload=payload,
            timeout_seconds=timeout_seconds if timeout_seconds is not None else self._default_timeout_seconds,
        )
        await self._command_log.mark_responded(command_id, outcome.status, outcome.result)
        return CommandResult(command_id=command_id, status=outcome.status, result=outcome.result)

    async def send_set_charging_profile(
        self,
        charger_id: str,
        tenant_id: uuid.UUID,
        connector_id: int,
        requested_watts: int,
        capacity_provider: ConnectorCapacityProvider,
        profile_payload: dict,
    ) -> CommandResult:
        max_power = await capacity_provider.get_max_power_watts(charger_id, connector_id)
        if max_power is not None and requested_watts > max_power:
            raise ChargingProfileExceedsCapacityError(
                f"requested {requested_watts}W exceeds connector max {max_power}W"
            )
        return await self.send_command(charger_id, tenant_id, "SetChargingProfile", profile_payload)

    async def start_firmware_update(
        self, charger_id: str, tenant_id: uuid.UUID, version: str, signed_url: str
    ) -> CommandResult:
        await self._firmware_store.start_update(charger_id, tenant_id, version)
        return await self.send_command(
            charger_id, tenant_id, "UpdateFirmware", {"location": signed_url, "version": version}
        )

    async def handle_firmware_status_notification(self, charger_id: str, version: str, status: str) -> FirmwareUpdateRecord:
        return await self._firmware_store.update_status(charger_id, version, status)

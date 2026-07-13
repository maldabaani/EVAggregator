"""Transaction lifecycle: read access for session recovery (Task 2.1) plus
start/stop for the inbound message handlers (Task 2.2).

`transaction_id` is the natural idempotency key for `StopTransaction`: if the
charger retries the message (common when it doesn't see a confirmation),
stopping an already-completed transaction must be a no-op, not a second
close-out or a second downstream event.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol


@dataclass
class ActiveTransaction:
    id: uuid.UUID
    charger_id: str
    connector_id: int
    id_tag: str
    # Additive field for live session status (elapsed time) — defaulted so
    # the existing Supabase/test call sites that don't yet supply it keep
    # working unchanged.
    start_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class StopResult:
    already_stopped: bool
    tenant_id: uuid.UUID | None = None
    charger_id: str | None = None


class UnknownTransactionError(Exception):
    pass


class TransactionRepository(Protocol):
    async def get_active_transaction(self, charger_id: str) -> ActiveTransaction | None: ...

    async def start_transaction(
        self,
        charger_id: str,
        tenant_id: uuid.UUID,
        connector_id: int,
        id_tag: str,
        meter_start: int,
        start_timestamp: datetime,
    ) -> ActiveTransaction: ...

    async def stop_transaction(
        self,
        transaction_id: uuid.UUID,
        meter_stop: int,
        stop_timestamp: datetime,
        reason: str | None,
    ) -> StopResult: ...


class InMemoryTransactionRepository:
    def __init__(self) -> None:
        self._active: dict[str, ActiveTransaction] = {}
        self._records: dict[uuid.UUID, dict] = {}

    def seed_active_transaction(self, charger_id: str, transaction: ActiveTransaction) -> None:
        self._active[charger_id] = transaction
        self._records[transaction.id] = {
            "status": "active",
            "tenant_id": None,
            "charger_id": charger_id,
        }

    async def get_active_transaction(self, charger_id: str) -> ActiveTransaction | None:
        return self._active.get(charger_id)

    async def start_transaction(
        self,
        charger_id: str,
        tenant_id: uuid.UUID,
        connector_id: int,
        id_tag: str,
        meter_start: int,
        start_timestamp: datetime,
    ) -> ActiveTransaction:
        transaction_id = uuid.uuid4()
        txn = ActiveTransaction(
            id=transaction_id, charger_id=charger_id, connector_id=connector_id, id_tag=id_tag,
            start_timestamp=start_timestamp,
        )
        self._active[charger_id] = txn
        self._records[transaction_id] = {
            "status": "active",
            "tenant_id": tenant_id,
            "charger_id": charger_id,
            "meter_start": meter_start,
            "start_timestamp": start_timestamp,
        }
        return txn

    async def stop_transaction(
        self,
        transaction_id: uuid.UUID,
        meter_stop: int,
        stop_timestamp: datetime,
        reason: str | None,
    ) -> StopResult:
        record = self._records.get(transaction_id)
        if record is None:
            raise UnknownTransactionError(f"unknown transaction_id: {transaction_id}")

        if record["status"] == "completed":
            return StopResult(already_stopped=True, tenant_id=record["tenant_id"], charger_id=record["charger_id"])

        record["status"] = "completed"
        record["meter_stop"] = meter_stop
        record["stop_timestamp"] = stop_timestamp
        record["reason"] = reason

        charger_id = record["charger_id"]
        active = self._active.get(charger_id)
        if active is not None and active.id == transaction_id:
            del self._active[charger_id]

        return StopResult(already_stopped=False, tenant_id=record["tenant_id"], charger_id=charger_id)

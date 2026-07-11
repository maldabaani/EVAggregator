"""Read access to in-flight transactions for session recovery (Task 2.1).
Full transaction lifecycle (start/stop) is owned by Task 2.2's message
handlers — this module only needs to answer "is there an active transaction
for this charger" on reconnect.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass
class ActiveTransaction:
    id: uuid.UUID
    charger_id: str
    connector_id: int
    id_tag: str


class TransactionRepository(Protocol):
    async def get_active_transaction(self, charger_id: str) -> ActiveTransaction | None: ...


class InMemoryTransactionRepository:
    def __init__(self) -> None:
        self._active: dict[str, ActiveTransaction] = {}

    def seed_active_transaction(self, charger_id: str, transaction: ActiveTransaction) -> None:
        self._active[charger_id] = transaction

    async def get_active_transaction(self, charger_id: str) -> ActiveTransaction | None:
        return self._active.get(charger_id)

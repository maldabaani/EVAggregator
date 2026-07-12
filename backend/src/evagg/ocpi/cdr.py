"""Task 1.2 — CDR generation on `StopTransaction` and push to the roaming
partner, both idempotent: at-least-once event delivery must never generate a
second CDR for the same session, and a retried push must never deliver the
same CDR twice to a partner. CDRs are immutable once sent — corrections are
a new credit/debit CDR referencing the original, never an edit (Task 1.1's
`OCPICdr` domain model has no update path for this reason).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable, Protocol

from evagg.ocpi.domain import OCPICdr

MISMATCH_THRESHOLD_FRACTION = 0.02  # 2%, per Task 1.2's acceptance criteria


class CdrStore(Protocol):
    async def get_by_session(self, session_id: str) -> OCPICdr | None: ...

    async def save(self, session_id: str, cdr: OCPICdr) -> None: ...


class InMemoryCdrStore:
    def __init__(self) -> None:
        self._by_session: dict[str, OCPICdr] = {}

    async def get_by_session(self, session_id: str) -> OCPICdr | None:
        return self._by_session.get(session_id)

    async def save(self, session_id: str, cdr: OCPICdr) -> None:
        self._by_session[session_id] = cdr


class CdrPushClient(Protocol):
    async def push_cdr(self, partner_id: uuid.UUID, cdr: OCPICdr) -> None: ...


class InMemoryCdrPushClient:
    def __init__(self) -> None:
        self.pushed: list[tuple[uuid.UUID, str]] = []

    async def push_cdr(self, partner_id: uuid.UUID, cdr: OCPICdr) -> None:
        self.pushed.append((partner_id, cdr.id))


class CdrService:
    def __init__(self, store: CdrStore, push_client: CdrPushClient) -> None:
        self._store = store
        self._push_client = push_client
        self._pushed: set[tuple[uuid.UUID, str]] = set()

    async def generate_cdr_on_stop_transaction(self, session_id: str, cdr_factory: Callable[[], OCPICdr]) -> OCPICdr:
        """`cdr_factory` is only invoked if no CDR exists yet for this
        session — a retried stop_transaction event must not mint a second
        CDR (or a second cdr_id) for the same session."""
        existing = await self._store.get_by_session(session_id)
        if existing is not None:
            return existing

        cdr = cdr_factory()
        await self._store.save(session_id, cdr)
        return cdr

    async def push_cdr_idempotent(self, partner_id: uuid.UUID, cdr: OCPICdr) -> None:
        dedup_key = (partner_id, cdr.id)
        if dedup_key in self._pushed:
            return
        await self._push_client.push_cdr(partner_id, cdr)
        self._pushed.add(dedup_key)


@dataclass(frozen=True)
class ReconciliationResult:
    status: str  # 'matched' | 'mismatched'
    delta_fraction: float


def reconcile_incoming_cdr(local_kwh: float, partner_kwh: float) -> ReconciliationResult:
    """Task 1.2 — as eMSP, reconcile an incoming partner CDR against the
    local session record; flags mismatches (kWh delta > 2%) for review."""
    if local_kwh == 0:
        delta_fraction = 0.0 if partner_kwh == 0 else 1.0
    else:
        delta_fraction = abs(partner_kwh - local_kwh) / local_kwh
    status = "mismatched" if delta_fraction > MISMATCH_THRESHOLD_FRACTION else "matched"
    return ReconciliationResult(status=status, delta_fraction=delta_fraction)

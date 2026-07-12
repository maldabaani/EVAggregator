"""Task 3.4 — B2B invoicing cycle. An invoice is immutable once issued;
corrections go through a linked credit note (`InvoiceAdjustment`), never an
in-place edit — the same immutability pattern as Epic 1's OCPI CDRs.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Protocol


class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    ISSUED = "issued"
    PAID = "paid"
    OVERDUE = "overdue"


class InvoiceImmutableError(Exception):
    pass


class InvoiceNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    account_id: uuid.UUID
    timestamp: datetime
    amount_minor_units: int


@dataclass
class Invoice:
    id: uuid.UUID
    tenant_id: uuid.UUID
    account_id: uuid.UUID
    period_start: datetime
    period_end: datetime
    status: str
    total_minor_units: int
    due_at: datetime | None = None
    pdf_url: str | None = None


@dataclass(frozen=True)
class InvoiceAdjustment:
    id: uuid.UUID
    invoice_id: uuid.UUID
    amount_minor_units: int  # signed delta
    reason: str


class InvoiceStore(Protocol):
    async def create(
        self, tenant_id: uuid.UUID, account_id: uuid.UUID, period_start: datetime, period_end: datetime,
        total_minor_units: int, due_at: datetime | None = None,
    ) -> Invoice: ...

    async def get(self, invoice_id: uuid.UUID) -> Invoice | None: ...

    async def update_status(self, invoice_id: uuid.UUID, status: InvoiceStatus) -> None: ...

    async def set_total(self, invoice_id: uuid.UUID, total_minor_units: int) -> None: ...

    async def apply_adjustment(self, adjustment: InvoiceAdjustment) -> None: ...


@dataclass
class InMemoryInvoiceStore:
    _invoices: dict[uuid.UUID, Invoice] = field(default_factory=dict)
    _adjustments: list[InvoiceAdjustment] = field(default_factory=list)

    async def create(
        self, tenant_id: uuid.UUID, account_id: uuid.UUID, period_start: datetime, period_end: datetime,
        total_minor_units: int, due_at: datetime | None = None,
    ) -> Invoice:
        invoice = Invoice(
            id=uuid.uuid4(), tenant_id=tenant_id, account_id=account_id, period_start=period_start,
            period_end=period_end, status=InvoiceStatus.DRAFT.value, total_minor_units=total_minor_units, due_at=due_at,
        )
        self._invoices[invoice.id] = invoice
        return invoice

    async def get(self, invoice_id: uuid.UUID) -> Invoice | None:
        return self._invoices.get(invoice_id)

    async def update_status(self, invoice_id: uuid.UUID, status: InvoiceStatus) -> None:
        self._invoices[invoice_id].status = status.value

    async def set_total(self, invoice_id: uuid.UUID, total_minor_units: int) -> None:
        self._invoices[invoice_id].total_minor_units = total_minor_units

    async def apply_adjustment(self, adjustment: InvoiceAdjustment) -> None:
        self._adjustments.append(adjustment)
        self._invoices[adjustment.invoice_id].total_minor_units += adjustment.amount_minor_units

    def adjustments_for(self, invoice_id: uuid.UUID) -> list[InvoiceAdjustment]:
        return [a for a in self._adjustments if a.invoice_id == invoice_id]


class InvoiceGenerationService:
    def __init__(self, store: InvoiceStore) -> None:
        self._store = store

    async def generate_for_period(
        self,
        tenant_id: uuid.UUID,
        account_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
        sessions: list[SessionRecord],
        due_at: datetime | None = None,
    ) -> Invoice:
        """Sums exactly the sessions whose timestamp falls within
        [period_start, period_end) — a session belongs to exactly one
        billing period, never double-counted across an adjacent run."""
        relevant = [s for s in sessions if period_start <= s.timestamp < period_end]
        total = sum(s.amount_minor_units for s in relevant)
        return await self._store.create(tenant_id, account_id, period_start, period_end, total, due_at)


class InvoiceService:
    def __init__(self, store: InvoiceStore) -> None:
        self._store = store

    async def issue(self, invoice_id: uuid.UUID) -> None:
        await self._store.update_status(invoice_id, InvoiceStatus.ISSUED)

    async def edit_draft(self, invoice_id: uuid.UUID, new_total_minor_units: int) -> None:
        invoice = await self._store.get(invoice_id)
        if invoice is None:
            raise InvoiceNotFoundError(str(invoice_id))
        if invoice.status != InvoiceStatus.DRAFT.value:
            raise InvoiceImmutableError(
                f"invoice {invoice_id} is {invoice.status}; only draft invoices can be edited directly"
            )
        await self._store.set_total(invoice_id, new_total_minor_units)

    async def apply_credit_note(
        self, invoice_id: uuid.UUID, amount_minor_units: int, reason: str
    ) -> InvoiceAdjustment:
        invoice = await self._store.get(invoice_id)
        if invoice is None:
            raise InvoiceNotFoundError(str(invoice_id))
        adjustment = InvoiceAdjustment(
            id=uuid.uuid4(), invoice_id=invoice_id, amount_minor_units=amount_minor_units, reason=reason
        )
        await self._store.apply_adjustment(adjustment)
        return adjustment

    async def mark_overdue_if_past_due(self, invoice_id: uuid.UUID, now: datetime) -> None:
        invoice = await self._store.get(invoice_id)
        if invoice is None:
            raise InvoiceNotFoundError(str(invoice_id))
        if invoice.status == InvoiceStatus.ISSUED.value and invoice.due_at is not None and now > invoice.due_at:
            await self._store.update_status(invoice_id, InvoiceStatus.OVERDUE)

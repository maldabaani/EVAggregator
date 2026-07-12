from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from evagg.billing.invoicing import (
    InMemoryInvoiceStore,
    InvoiceGenerationService,
    InvoiceImmutableError,
    InvoiceService,
    SessionRecord,
)

TENANT_ID = uuid.uuid4()
ACCOUNT_ID = uuid.uuid4()


def _session(days_into_period: int, amount: int) -> SessionRecord:
    return SessionRecord(
        session_id=str(uuid.uuid4()),
        account_id=ACCOUNT_ID,
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=days_into_period),
        amount_minor_units=amount,
    )


@pytest.mark.asyncio
async def test_invoice_generation_covers_exact_billing_period_no_overlap():
    store = InMemoryInvoiceStore()
    service = InvoiceGenerationService(store)
    period_start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    period_end = datetime(2026, 2, 1, tzinfo=timezone.utc)

    sessions = [
        _session(-1, 1000),  # Dec 31 — before the period, must be excluded
        _session(0, 500),  # Jan 1 — start boundary, included
        _session(15, 700),  # mid-period, included
        _session(31, 900),  # Feb 1 — end boundary, must be excluded (next period's)
    ]

    invoice = await service.generate_for_period(TENANT_ID, ACCOUNT_ID, period_start, period_end, sessions)

    assert invoice.total_minor_units == 500 + 700


@pytest.mark.asyncio
async def test_invoice_generation_across_two_adjacent_periods_never_double_counts():
    store = InMemoryInvoiceStore()
    service = InvoiceGenerationService(store)
    jan_start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    jan_end = feb_start = datetime(2026, 2, 1, tzinfo=timezone.utc)
    feb_end = datetime(2026, 3, 1, tzinfo=timezone.utc)

    sessions = [_session(15, 700), _session(45, 900)]  # one in Jan, one in Feb

    jan_invoice = await service.generate_for_period(TENANT_ID, ACCOUNT_ID, jan_start, jan_end, sessions)
    feb_invoice = await service.generate_for_period(TENANT_ID, ACCOUNT_ID, feb_start, feb_end, sessions)

    assert jan_invoice.total_minor_units == 700
    assert feb_invoice.total_minor_units == 900


@pytest.mark.asyncio
async def test_issued_invoice_cannot_be_edited_directly():
    store = InMemoryInvoiceStore()
    generation = InvoiceGenerationService(store)
    service = InvoiceService(store)
    invoice = await generation.generate_for_period(
        TENANT_ID, ACCOUNT_ID, datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 2, 1, tzinfo=timezone.utc), []
    )
    await service.issue(invoice.id)

    with pytest.raises(InvoiceImmutableError):
        await service.edit_draft(invoice.id, new_total_minor_units=99999)


@pytest.mark.asyncio
async def test_draft_invoice_can_be_edited_directly():
    store = InMemoryInvoiceStore()
    generation = InvoiceGenerationService(store)
    service = InvoiceService(store)
    invoice = await generation.generate_for_period(
        TENANT_ID, ACCOUNT_ID, datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 2, 1, tzinfo=timezone.utc), []
    )

    await service.edit_draft(invoice.id, new_total_minor_units=1234)

    updated = await store.get(invoice.id)
    assert updated.total_minor_units == 1234


@pytest.mark.asyncio
async def test_credit_note_correctly_adjusts_invoice_total():
    store = InMemoryInvoiceStore()
    generation = InvoiceGenerationService(store)
    service = InvoiceService(store)
    invoice = await generation.generate_for_period(
        TENANT_ID, ACCOUNT_ID, datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 2, 1, tzinfo=timezone.utc),
        [_session(1, 5000)],
    )
    await service.issue(invoice.id)

    await service.apply_credit_note(invoice.id, amount_minor_units=-500, reason="billing dispute")

    updated = await store.get(invoice.id)
    assert updated.total_minor_units == 4500
    assert len(store.adjustments_for(invoice.id)) == 1


@pytest.mark.asyncio
async def test_credit_note_does_not_bypass_immutability_via_edit_draft():
    """Corrections must go through apply_credit_note, not edit_draft, once issued."""
    store = InMemoryInvoiceStore()
    generation = InvoiceGenerationService(store)
    service = InvoiceService(store)
    invoice = await generation.generate_for_period(
        TENANT_ID, ACCOUNT_ID, datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 2, 1, tzinfo=timezone.utc),
        [_session(1, 5000)],
    )
    await service.issue(invoice.id)

    with pytest.raises(InvoiceImmutableError):
        await service.edit_draft(invoice.id, new_total_minor_units=0)

    # The credit note path still works despite the invoice being issued.
    await service.apply_credit_note(invoice.id, amount_minor_units=-500, reason="dispute")
    updated = await store.get(invoice.id)
    assert updated.total_minor_units == 4500


@pytest.mark.asyncio
async def test_invoice_status_transitions_to_overdue_after_due_date():
    store = InMemoryInvoiceStore()
    generation = InvoiceGenerationService(store)
    service = InvoiceService(store)
    due_at = datetime(2026, 2, 15, tzinfo=timezone.utc)
    invoice = await generation.generate_for_period(
        TENANT_ID, ACCOUNT_ID, datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 2, 1, tzinfo=timezone.utc),
        [], due_at=due_at,
    )
    await service.issue(invoice.id)

    await service.mark_overdue_if_past_due(invoice.id, now=due_at + timedelta(days=1))

    updated = await store.get(invoice.id)
    assert updated.status == "overdue"


@pytest.mark.asyncio
async def test_invoice_not_yet_past_due_date_stays_issued():
    store = InMemoryInvoiceStore()
    generation = InvoiceGenerationService(store)
    service = InvoiceService(store)
    due_at = datetime(2026, 2, 15, tzinfo=timezone.utc)
    invoice = await generation.generate_for_period(
        TENANT_ID, ACCOUNT_ID, datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 2, 1, tzinfo=timezone.utc),
        [], due_at=due_at,
    )
    await service.issue(invoice.id)

    await service.mark_overdue_if_past_due(invoice.id, now=due_at - timedelta(days=1))

    updated = await store.get(invoice.id)
    assert updated.status == "issued"

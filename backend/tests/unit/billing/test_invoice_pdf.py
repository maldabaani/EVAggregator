from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from evagg.billing.invoice_pdf import InMemoryObjectStorageClient, InvoicePdfService, StubInvoicePdfRenderer
from evagg.billing.invoicing import InMemoryInvoiceStore, InvoiceGenerationService

TENANT_ID = uuid.uuid4()
ACCOUNT_ID = uuid.uuid4()


@pytest.mark.asyncio
async def test_generated_pdf_is_uploaded_and_linked_from_invoice():
    store = InMemoryInvoiceStore()
    generation = InvoiceGenerationService(store)
    invoice = await generation.generate_for_period(
        TENANT_ID, ACCOUNT_ID, datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 2, 1, tzinfo=timezone.utc), []
    )
    storage = InMemoryObjectStorageClient()
    pdf_service = InvoicePdfService(StubInvoicePdfRenderer(), storage, store)

    url = await pdf_service.generate_and_attach(invoice)

    assert url.endswith(f"{invoice.id}.pdf")
    updated = await store.get(invoice.id)
    assert updated.pdf_url == url
    assert len(storage.uploaded) == 1

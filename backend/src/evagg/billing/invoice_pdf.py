"""Task 3.4 — invoice PDF rendering + object storage, linked from
`invoice.pdf_url`. Kept as a thin seam: swapping the real PDF library or
object-storage backend later never touches invoicing/payout logic.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from evagg.billing.invoicing import Invoice, InvoiceStore


class InvoicePdfRenderer(Protocol):
    def render(self, invoice: Invoice) -> bytes: ...


class ObjectStorageClient(Protocol):
    async def upload(self, key: str, content: bytes) -> str:
        """Returns the stored object's public/internal URL."""
        ...


class StubInvoicePdfRenderer:
    def render(self, invoice: Invoice) -> bytes:
        return f"INVOICE {invoice.id}\nTotal: {invoice.total_minor_units}".encode("utf-8")


class InMemoryObjectStorageClient:
    def __init__(self) -> None:
        self.uploaded: dict[str, bytes] = {}

    async def upload(self, key: str, content: bytes) -> str:
        self.uploaded[key] = content
        return f"https://storage.example.com/{key}"


class InvoicePdfService:
    def __init__(self, renderer: InvoicePdfRenderer, storage: ObjectStorageClient, store: InvoiceStore) -> None:
        self._renderer = renderer
        self._storage = storage
        self._store = store

    async def generate_and_attach(self, invoice: Invoice) -> str:
        pdf_bytes = self._renderer.render(invoice)
        key = f"invoices/{invoice.tenant_id}/{invoice.id}.pdf"
        url = await self._storage.upload(key, pdf_bytes)
        await self._attach_url(invoice.id, url)
        return url

    async def _attach_url(self, invoice_id: uuid.UUID, url: str) -> None:
        invoice = await self._store.get(invoice_id)
        if invoice is not None:
            invoice.pdf_url = url

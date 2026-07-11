"""Task 1.3 — operator portal backend: partner token rotation, per-partner
price list scheduling, and the nightly CDR reconciliation job + CSV export.
"""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


# --- Token rotation ----------------------------------------------------


async def rotate_token_a(registry, partner_id: uuid.UUID, new_token_a: str) -> None:
    """Invalidates the partner's old token_a; the new one is required on the
    next handshake. `registry` is `evagg.ocpi.partner_store.PartnerRegistry`
    extended with `rotate_token_a` (see `InMemoryPartnerRegistry` there)."""
    await registry.rotate_token_a(partner_id, new_token_a)


# --- Price lists ---------------------------------------------------------


@dataclass(frozen=True)
class PartnerPriceList:
    partner_id: uuid.UUID
    connector_type: str
    tariff_id: uuid.UUID
    effective_from: datetime


class PriceListStore(Protocol):
    async def attach(self, price_list: PartnerPriceList) -> None: ...

    async def get_active(self, partner_id: uuid.UUID, connector_type: str, at: datetime) -> PartnerPriceList | None: ...


class InMemoryPriceListStore:
    def __init__(self) -> None:
        self._entries: list[PartnerPriceList] = []

    async def attach(self, price_list: PartnerPriceList) -> None:
        self._entries.append(price_list)

    async def get_active(self, partner_id: uuid.UUID, connector_type: str, at: datetime) -> PartnerPriceList | None:
        candidates = [
            entry
            for entry in self._entries
            if entry.partner_id == partner_id and entry.connector_type == connector_type and entry.effective_from <= at
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda entry: entry.effective_from)


# --- Reconciliation --------------------------------------------------------

AMOUNT_MISMATCH_THRESHOLD_FRACTION = 0.02


@dataclass(frozen=True)
class ReconciliationEntry:
    local_cdr_id: str | None
    partner_cdr_uid: str
    status: str  # 'matched' | 'mismatched' | 'pending'
    delta_fraction: float | None = None


def reconcile_cdr_batch(
    local_totals_by_cdr_id: dict[str, float],
    partner_reports: list[tuple[str, str | None, float]],
    amount_mismatch_threshold_fraction: float = AMOUNT_MISMATCH_THRESHOLD_FRACTION,
) -> list[ReconciliationEntry]:
    """`partner_reports` is (partner_cdr_uid, matched_local_cdr_id_or_None,
    partner_total_cost) per partner-confirmed CDR. A partner CDR with no
    matching local CDR id is reported `pending`, not silently dropped."""
    results: list[ReconciliationEntry] = []
    for partner_cdr_uid, local_cdr_id, partner_total in partner_reports:
        if local_cdr_id is None or local_cdr_id not in local_totals_by_cdr_id:
            results.append(ReconciliationEntry(local_cdr_id=local_cdr_id, partner_cdr_uid=partner_cdr_uid, status="pending"))
            continue

        local_total = local_totals_by_cdr_id[local_cdr_id]
        if local_total == 0:
            delta_fraction = 0.0 if partner_total == 0 else 1.0
        else:
            delta_fraction = abs(partner_total - local_total) / local_total

        status = "mismatched" if delta_fraction > amount_mismatch_threshold_fraction else "matched"
        results.append(
            ReconciliationEntry(
                local_cdr_id=local_cdr_id, partner_cdr_uid=partner_cdr_uid, status=status, delta_fraction=delta_fraction
            )
        )
    return results


def filter_reconciliation_entries(
    entries: list[ReconciliationEntry], status: str | None = None
) -> list[ReconciliationEntry]:
    if status is None:
        return entries
    return [entry for entry in entries if entry.status == status]


class ReconciliationResultStore(Protocol):
    async def save_batch(self, entries: list[ReconciliationEntry], run_at: datetime) -> None: ...

    async def query(self, from_: datetime | None = None, to: datetime | None = None) -> list[ReconciliationEntry]: ...


class InMemoryReconciliationResultStore:
    """Backs the nightly job's output for the portal's Reconciliation tab.
    Production persists to `ocpi_reconciliation_result` (Task 6.1)."""

    def __init__(self) -> None:
        self._runs: list[tuple[datetime, list[ReconciliationEntry]]] = []

    async def save_batch(self, entries: list[ReconciliationEntry], run_at: datetime) -> None:
        self._runs.append((run_at, entries))

    async def query(self, from_: datetime | None = None, to: datetime | None = None) -> list[ReconciliationEntry]:
        results: list[ReconciliationEntry] = []
        for run_at, entries in self._runs:
            if from_ is not None and run_at < from_:
                continue
            if to is not None and run_at > to:
                continue
            results.extend(entries)
        return results


def export_reconciliation_csv(entries: list[ReconciliationEntry]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["local_cdr_id", "partner_cdr_uid", "status", "delta_fraction"])
    for entry in entries:
        writer.writerow(
            [
                entry.local_cdr_id or "",
                entry.partner_cdr_uid,
                entry.status,
                f"{entry.delta_fraction:.4f}" if entry.delta_fraction is not None else "",
            ]
        )
    return buffer.getvalue()

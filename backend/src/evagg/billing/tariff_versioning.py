"""Task 3.2 — tariff versioning: a session is always billed against the
version active at its `start_timestamp`, never the latest, so a later tariff
edit can never retroactively change an already-started session's price.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class TariffVersionRecord:
    id: uuid.UUID
    tariff_id: uuid.UUID
    version_no: int
    effective_from: datetime
    effective_to: datetime | None


class TariffVersionStore(Protocol):
    async def add_version(
        self, tariff_id: uuid.UUID, version_no: int, effective_from: datetime, effective_to: datetime | None = None
    ) -> TariffVersionRecord: ...

    async def get_active_version(self, tariff_id: uuid.UUID, at: datetime) -> TariffVersionRecord | None: ...


class InMemoryTariffVersionStore:
    def __init__(self) -> None:
        self._versions: list[TariffVersionRecord] = []

    async def add_version(
        self, tariff_id: uuid.UUID, version_no: int, effective_from: datetime, effective_to: datetime | None = None
    ) -> TariffVersionRecord:
        record = TariffVersionRecord(
            id=uuid.uuid4(), tariff_id=tariff_id, version_no=version_no,
            effective_from=effective_from, effective_to=effective_to,
        )
        self._versions.append(record)
        return record

    async def get_active_version(self, tariff_id: uuid.UUID, at: datetime) -> TariffVersionRecord | None:
        candidates = [
            v for v in self._versions
            if v.tariff_id == tariff_id and v.effective_from <= at and (v.effective_to is None or at < v.effective_to)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda v: v.effective_from)

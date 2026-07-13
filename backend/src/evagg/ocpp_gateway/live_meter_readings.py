"""Latest-known-reading cache, keyed by transaction id — separate from
`MeterValueBuffer`'s durable, batched writes (Task 2.2). That buffer can
sit unflushed for up to `flush_interval_seconds`, which is fine for
storage but too stale for "what's this session's energy/power right
now" — so every inbound MeterValues reading is mirrored here
synchronously, independent of the buffer's flush cadence.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from evagg.ocpp_gateway.meter_values import MeterReading


class LatestMeterReadingStore(Protocol):
    async def update(self, reading: MeterReading) -> None: ...

    async def get_latest(self, transaction_id: uuid.UUID, measurand: str) -> MeterReading | None: ...


class InMemoryLatestMeterReadingStore:
    def __init__(self) -> None:
        self._latest: dict[uuid.UUID, dict[str, MeterReading]] = {}

    async def update(self, reading: MeterReading) -> None:
        by_measurand = self._latest.setdefault(reading.transaction_id, {})
        existing = by_measurand.get(reading.measurand)
        # A MeterValues frame's readings aren't guaranteed to arrive in
        # timestamp order across retries/duplicate frames — keep whichever
        # is actually newest rather than whatever arrived most recently.
        if existing is None or reading.ts >= existing.ts:
            by_measurand[reading.measurand] = reading

    async def get_latest(self, transaction_id: uuid.UUID, measurand: str) -> MeterReading | None:
        return self._latest.get(transaction_id, {}).get(measurand)

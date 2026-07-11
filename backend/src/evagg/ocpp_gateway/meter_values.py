"""MeterValues ingestion (Task 2.2) — the highest-volume path. Batches rows
in memory and flushes on whichever comes first: `max_batch_size` rows
accumulated, or `flush_interval_seconds` elapsed since the buffer's oldest
row — rather than one write per inbound message, to protect the DB under
load.

The buffer only checks its time-based threshold when a new row arrives (no
background timer here), so callers must also flush explicitly at points where
no further meter values are expected for a while — e.g. `StopTransaction`
must flush before the session record closes, or trailing readings could sit
unwritten indefinitely.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol


@dataclass(frozen=True)
class MeterReading:
    tenant_id: uuid.UUID
    transaction_id: uuid.UUID
    charger_id: str
    ts: datetime
    measurand: str
    value: float
    unit: str


class MeterValueSink(Protocol):
    async def write_batch(self, rows: list[MeterReading]) -> None: ...


class InMemoryMeterValueSink:
    def __init__(self) -> None:
        self.batches: list[list[MeterReading]] = []

    async def write_batch(self, rows: list[MeterReading]) -> None:
        self.batches.append(list(rows))

    @property
    def all_written_rows(self) -> list[MeterReading]:
        return [row for batch in self.batches for row in batch]


class MeterValueBuffer:
    def __init__(
        self,
        sink: MeterValueSink,
        max_batch_size: int = 50,
        flush_interval_seconds: float = 2.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._sink = sink
        self._max_batch_size = max_batch_size
        self._flush_interval_seconds = flush_interval_seconds
        self._clock = clock
        self._buffer: list[MeterReading] = []
        self._buffer_opened_at: float | None = None

    @property
    def pending_count(self) -> int:
        return len(self._buffer)

    async def add(self, reading: MeterReading) -> None:
        if not self._buffer:
            self._buffer_opened_at = self._clock()
        self._buffer.append(reading)
        if self._should_flush():
            await self.flush()

    def _should_flush(self) -> bool:
        if len(self._buffer) >= self._max_batch_size:
            return True
        if self._buffer_opened_at is not None and (self._clock() - self._buffer_opened_at) >= self._flush_interval_seconds:
            return True
        return False

    async def flush(self) -> None:
        if not self._buffer:
            return
        rows, self._buffer = self._buffer, []
        self._buffer_opened_at = None
        await self._sink.write_batch(rows)

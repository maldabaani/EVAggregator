"""OCPP operational state: transactions, outbound command log, firmware updates.

High-volume time-series data (`meter_value`, `status_log`) lives in
`evagg.models.timeseries` as TimescaleDB hypertables, kept separate from these
regular OLTP tables per Task 6.2's isolation-from-OLTP requirement.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from evagg.models.base import Base, TenantScopedMixin


class Transaction(Base, TenantScopedMixin):
    __tablename__ = "transaction"

    charger_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("charger.id"), nullable=False, index=True
    )
    connector_id: Mapped[int] = mapped_column(Integer, nullable=False)
    id_tag: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    meter_start: Mapped[int] = mapped_column(Integer, nullable=False)  # Wh
    meter_stop: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stop_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")  # 'active'|'completed'
    stop_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payment_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # 'pending'|'charged'|'payment_failed'


class CommandLog(Base, TenantScopedMixin):
    __tablename__ = "command_log"

    charger_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("charger.id"), nullable=False, index=True
    )
    command_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True, index=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # 'pending'|'accepted'|'rejected'|'timed_out'
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class FirmwareUpdate(Base, TenantScopedMixin):
    __tablename__ = "firmware_update"

    charger_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("charger.id"), nullable=False, index=True
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # 'pending'|'downloading'|'installing'|'installed'|'failed'

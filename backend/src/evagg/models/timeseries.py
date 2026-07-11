"""TimescaleDB hypertables: high-volume meter readings and charger status log.

These use a composite primary key `(id, ts)` rather than `id` alone, because
TimescaleDB requires the partitioning column (`ts`) to be part of any primary
key / unique constraint on a hypertable (see Task 6.2). The tables are created
as regular Postgres tables by Alembic; a follow-up migration step calls
`create_hypertable(...)` to convert them, keeping DDL declarative here and the
Timescale-specific conversion explicit in the migration.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, PrimaryKeyConstraint, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from evagg.models.base import Base, TENANT_SCOPED_TABLES, TimestampMixin


class MeterValue(Base, TimestampMixin):
    __tablename__ = "meter_value"
    __table_args__ = (PrimaryKeyConstraint("id", "ts", name="pk_meter_value"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), server_default=text("gen_random_uuid()"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transaction.id"), nullable=False, index=True
    )
    charger_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("charger.id"), nullable=False, index=True
    )
    measurand: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)


class StatusLog(Base, TimestampMixin):
    __tablename__ = "status_log"
    __table_args__ = (PrimaryKeyConstraint("id", "ts", name="pk_status_log"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), server_default=text("gen_random_uuid()"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    charger_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("charger.id"), nullable=False, index=True
    )
    connector_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)


# Hypertables are tenant-scoped like every other table, even though they can't
# use TenantScopedMixin's single-column PK — register them explicitly so the
# RLS audit script (Task 4.1) still covers them.
TENANT_SCOPED_TABLES.add(MeterValue.__tablename__)
TENANT_SCOPED_TABLES.add(StatusLog.__tablename__)

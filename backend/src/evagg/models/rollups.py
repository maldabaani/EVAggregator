"""Pre-aggregated daily rollup tables, populated by nightly jobs, so dashboards
never scan raw session tables directly (Task 4.4, Task 5.4).
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from evagg.models.base import Base, TenantScopedMixin


class TeamDriverDailyUsage(Base, TenantScopedMixin):
    __tablename__ = "team_driver_daily_usage"
    __table_args__ = (
        UniqueConstraint(
            "team_id", "driver_id", "usage_date", name="uq_team_driver_daily_usage_team_driver_date"
        ),
    )

    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("team.id"), nullable=False, index=True
    )
    driver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("driver.id"), nullable=False, index=True
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("site.id"), nullable=True, index=True
    )
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    session_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    kwh_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # watt-hours
    cost_total_minor_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_complete: Mapped[bool] = mapped_column(nullable=False, default=True)


class DriverDailyUsage(Base, TenantScopedMixin):
    __tablename__ = "driver_daily_usage"
    __table_args__ = (
        UniqueConstraint("driver_id", "usage_date", name="uq_driver_daily_usage_driver_date"),
    )

    driver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("driver.id"), nullable=False, index=True
    )
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    session_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    kwh_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_total_minor_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

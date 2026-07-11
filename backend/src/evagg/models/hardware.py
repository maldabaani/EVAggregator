"""Hardware: chargers, connectors, and team-scoped visibility (Task 4.3)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from evagg.models.base import Base, TenantScopedMixin


class Charger(Base, TenantScopedMixin):
    __tablename__ = "charger"

    vendor: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    firmware_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # 'pending' | 'accepted' | 'rejected'
    visibility: Mapped[str] = mapped_column(String(20), nullable=False, default="public")
    # 'public' | 'team_only'
    ws_credential_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_boot_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Connector(Base, TenantScopedMixin):
    __tablename__ = "connector"
    __table_args__ = (
        UniqueConstraint("charger_id", "connector_id", name="uq_connector_charger_connector_id"),
    )

    charger_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("charger.id"), nullable=False, index=True
    )
    connector_id: Mapped[int] = mapped_column(Integer, nullable=False)  # OCPP connector number
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="Available")
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    max_power_watts: Mapped[int | None] = mapped_column(nullable=True)


class ChargerTeamAccess(Base, TenantScopedMixin):
    """Grants a team visibility into a `team_only` charger."""

    __tablename__ = "charger_team_access"
    __table_args__ = (
        UniqueConstraint("charger_id", "team_id", name="uq_charger_team_access_charger_team"),
    )

    charger_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("charger.id"), nullable=False, index=True
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("team.id"), nullable=False, index=True
    )

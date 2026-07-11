"""OCPI roaming: partner config, role config, sessions, CDRs, reconciliation."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from evagg.models.base import Base, TenantScopedMixin


class OcpiPartner(Base, TenantScopedMixin):
    __tablename__ = "ocpi_partner"

    party_id: Mapped[str] = mapped_column(String(3), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    negotiated_version: Mapped[str | None] = mapped_column(String(10), nullable=True)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    token_a: Mapped[str | None] = mapped_column(String(255), nullable=True)
    token_b: Mapped[str | None] = mapped_column(String(255), nullable=True)
    token_c: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    last_handshake_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OcpiRoleConfig(Base, TenantScopedMixin):
    """A tenant can hold both CPO and eMSP roles simultaneously."""

    __tablename__ = "ocpi_role_config"
    __table_args__ = (UniqueConstraint("tenant_id", "role", name="uq_ocpi_role_config_tenant_role"),)

    role: Mapped[str] = mapped_column(String(10), nullable=False)  # 'CPO' | 'EMSP'
    party_id: Mapped[str] = mapped_column(String(3), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)


class OcpiSession(Base, TenantScopedMixin):
    __tablename__ = "ocpi_session"

    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ocpi_partner.id"), nullable=False, index=True
    )
    local_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transaction.id"), nullable=True, index=True
    )
    external_session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    kwh: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # watt-hours, integer
    start_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OcpiCdr(Base, TenantScopedMixin):
    """Immutable once sent. Corrections use `correction_of` to reference the
    original CDR with a new credit/debit CDR — never an in-place edit."""

    __tablename__ = "ocpi_cdr"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ocpi_session.id"), nullable=False, index=True
    )
    cdr_uid: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    total_cost_minor_units: Mapped[int] = mapped_column(Integer, nullable=False)
    kwh: Mapped[int] = mapped_column(Integer, nullable=False)
    correction_of: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ocpi_cdr.id"), nullable=True, index=True
    )


class OcpiReconciliationResult(Base, TenantScopedMixin):
    __tablename__ = "ocpi_reconciliation_result"

    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ocpi_partner.id"), nullable=False, index=True
    )
    local_cdr_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ocpi_cdr.id"), nullable=True, index=True
    )
    partner_cdr_uid: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # 'matched' | 'mismatched' | 'pending'
    delta_minor_units: Mapped[int | None] = mapped_column(Integer, nullable=True)

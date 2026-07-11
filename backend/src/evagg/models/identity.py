"""Identity: drivers, operator (portal) users, and their credentials.

`driver.tenant_id` points at the owning organization for B2B fleet drivers; for
direct consumer drivers (not part of any fleet) it points at a reserved
"platform" organization row representing the direct-to-consumer tenant, so the
column stays NOT NULL and RLS still applies uniformly.
"""

from __future__ import annotations

import uuid

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from evagg.models.base import Base, TenantScopedMixin


class Driver(Base, TenantScopedMixin):
    __tablename__ = "driver"

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    autocharge_mac: Mapped[str | None] = mapped_column(String(17), nullable=True, index=True)
    carbon_country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    carbon_area_code: Mapped[str | None] = mapped_column(String(50), nullable=True)


class OperatorUser(Base, TenantScopedMixin):
    __tablename__ = "operator_user"

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="staff")  # 'admin' | 'staff'


class Credential(Base, TenantScopedMixin):
    """One row per auth method bound to a driver or operator_user.

    `subject_type`/`subject_id` form a polymorphic reference rather than two
    nullable FKs, since a credential belongs to exactly one subject kind.
    """

    __tablename__ = "credential"
    __table_args__ = (
        UniqueConstraint("subject_type", "subject_id", "credential_type", name="uq_credential_subject_type"),
    )

    subject_type: Mapped[str] = mapped_column(String(20), nullable=False)  # 'driver' | 'operator_user'
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    credential_type: Mapped[str] = mapped_column(String(20), nullable=False)  # 'password' | 'sso'
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sso_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sso_subject_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

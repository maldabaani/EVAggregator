"""Tenancy hierarchy: organization -> site -> team -> driver_team_membership.

`organization` is the tenant root itself (tenant_id elsewhere == organization.id),
so it intentionally does NOT use `TenantScopedMixin` — there is no "owning tenant"
above an organization. Every other table in this module is tenant-scoped.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from evagg.models.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class Organization(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "organization"

    name: Mapped[str] = mapped_column(String(255), nullable=False)


class Site(Base, TenantScopedMixin):
    __tablename__ = "site"

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Team(Base, TenantScopedMixin):
    __tablename__ = "team"

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False, index=True
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("site.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class DriverTeamMembership(Base, TenantScopedMixin):
    __tablename__ = "driver_team_membership"
    __table_args__ = (UniqueConstraint("driver_id", "team_id", name="uq_driver_team_membership_driver_team"),)

    driver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("driver.id"), nullable=False, index=True
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("team.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # 'admin' | 'member'


class TeamInvite(Base, TenantScopedMixin):
    """Join-code for Task 4.2 team onboarding."""

    __tablename__ = "team_invite"

    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("team.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    max_uses: Mapped[int] = mapped_column(nullable=False, default=1)
    used_count: Mapped[int] = mapped_column(nullable=False, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

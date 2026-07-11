"""Declarative base + shared mixins for every ORM model.

Every tenant-scoped table gets `id (uuid)`, `tenant_id`, `created_at`, `updated_at`
per the engineering standards doc. `TenantScopedMixin` also self-registers its
table name into `TENANT_SCOPED_TABLES`, which Task 4.1's RLS audit script
(`evagg.scripts.audit_rls`) uses to verify every such table has an active RLS
policy — no tenant-scoped table should ship without one.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, MetaData, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Populated at class-creation time by TenantScopedMixin subclasses. Consumed by
# the RLS audit script — the single source of truth for "which tables must have
# a tenant-isolation policy".
TENANT_SCOPED_TABLES: set[str] = set()


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPKMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TenantScopedMixin(UUIDPKMixin, TimestampMixin):
    """Base for every table scoped to a tenant (= `organization.id`)."""

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        tablename = cls.__dict__.get("__tablename__")
        if tablename:
            TENANT_SCOPED_TABLES.add(tablename)

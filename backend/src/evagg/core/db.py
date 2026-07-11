"""Async SQLAlchemy engine/session setup for the relational (OLTP) database.

Sized for the OCPP gateway's connection-per-request pattern (Task 6.1) — in
production this pool sits behind PgBouncer in transaction-pooling mode, so
`pool_size` here reflects the app-side pool talking to PgBouncer, not raw
Postgres connections.

Two engines are exposed:

- `engine` / `get_db`: the standard app connection pool, bound to the
  `evagg_app` DB role (no BYPASSRLS) — every query it runs is subject to RLS,
  scoped by `bind_tenant_context` (Task 4.1).
- `superadmin_engine` / `get_superadmin_db`: bound to `evagg_superadmin`
  (BYPASSRLS), used only by internal ops tooling, never by the standard
  request path. Every use is logged.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from evagg.core.config import settings
from evagg.core.tenancy import bind_tenant_context, log_superadmin_access, require_current_tenant

engine: AsyncEngine = create_async_engine(settings.database_url, pool_size=20, max_overflow=10, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

superadmin_engine: AsyncEngine = create_async_engine(settings.superadmin_database_url, pool_size=2, pool_pre_ping=True)
SuperadminSessionLocal = async_sessionmaker(superadmin_engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: a tenant-scoped session. Fails closed (401) if no
    tenant context was resolved by `TenantContextMiddleware`."""
    tenant_id = require_current_tenant()
    async with AsyncSessionLocal() as session:
        await bind_tenant_context(session, tenant_id)
        yield session


async def get_superadmin_db(actor: str = "internal-ops", reason: str = "unspecified") -> AsyncIterator[AsyncSession]:
    """FastAPI dependency for internal ops tooling only — bypasses RLS
    entirely via the DB role's BYPASSRLS attribute. Every call is logged."""
    await log_superadmin_access(actor=actor, reason=reason)
    async with SuperadminSessionLocal() as session:
        yield session

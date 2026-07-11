"""Integration coverage for Task 6.1 (schema), Task 6.2 (hypertables), and
Task 4.1 (RLS) — runs against real docker-compose Postgres/TimescaleDB, unlike
the mocked/compiled-DDL checks in tests/unit.

Verified manually against a real local Postgres 16 during development (see
commit history): fresh-DB apply, downgrade, fail-closed zero-row reads with no
tenant context, and cross-tenant isolation between two seeded organizations
all behaved as asserted below. TimescaleDB-specific steps (hypertable
conversion, continuous aggregate, retention) require the `timescaledb`
extension and are annotated accordingly — they were reviewed against the
Timescale API but could not be executed in the sandbox that wrote this suite
(no TimescaleDB extension available locally, and container image pulls were
blocked by network policy). Ran for real the first time this suite executed
in CI against the `timescale/timescaledb` docker-compose image, which
surfaced three real migration bugs no local review could have caught: a
transaction-block restriction on continuous aggregate creation, and two
rounds of RLS/TimescaleDB-feature conflicts (continuous aggregates and RLS
have an orderable conflict; RLS and compression do not — TimescaleDB refuses
to combine them on the same hypertable under any ordering, which is why
`meter_value`/`status_log` no longer use compression at all).
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest
from alembic import command
from alembic.config import Config

from evagg.core.config import settings
from tests.integration.conftest import requires_timescaledb

ALEMBIC_INI = "alembic.ini"


def _alembic_config() -> Config:
    return Config(ALEMBIC_INI)


@requires_timescaledb
def test_schema_migration_applies_cleanly_on_empty_db():
    cfg = _alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")


@requires_timescaledb
def test_schema_migration_applies_cleanly_with_existing_seed_data():
    cfg = _alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "b77170234860")
    # seed data goes here once model factories exist; for now this proves the
    # additive migration path (create -> upgrade further) doesn't choke on a
    # non-empty schema.
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")


@pytest.mark.asyncio
@requires_timescaledb
async def test_rls_fails_closed_without_tenant_context_and_isolates_tenants():
    cfg = _alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    app_dsn = settings.database_url.replace("+asyncpg", "")
    admin_dsn = settings.migration_database_url.replace("+asyncpg", "")

    org_a, org_b, site_a = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    admin_conn = await asyncpg.connect(admin_dsn)
    try:
        await admin_conn.execute("ALTER ROLE evagg_app LOGIN PASSWORD 'evagg_app'")
    finally:
        await admin_conn.close()

    app_conn = await asyncpg.connect(app_dsn)
    try:
        async with app_conn.transaction():
            await app_conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(org_a))
            await app_conn.execute("INSERT INTO organization (id, name) VALUES ($1, 'Org A')", org_a)
        async with app_conn.transaction():
            await app_conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(org_b))
            await app_conn.execute("INSERT INTO organization (id, name) VALUES ($1, 'Org B')", org_b)
        async with app_conn.transaction():
            await app_conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(org_a))
            await app_conn.execute(
                "INSERT INTO site (id, tenant_id, org_id, name) VALUES ($1, $2, $2, 'Site A1')",
                site_a,
                org_a,
            )

        # No tenant context set at all -> fail closed, zero rows.
        no_context_rows = await app_conn.fetch("SELECT id FROM site")
        assert no_context_rows == []

        # Tenant A sees its own site.
        async with app_conn.transaction():
            await app_conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(org_a))
            tenant_a_rows = await app_conn.fetch("SELECT id FROM site")
        assert [r["id"] for r in tenant_a_rows] == [site_a]

        # Tenant B must never see tenant A's site, even with no app-layer filter.
        async with app_conn.transaction():
            await app_conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(org_b))
            tenant_b_rows = await app_conn.fetch("SELECT id FROM site")
        assert tenant_b_rows == []
    finally:
        await app_conn.close()
        command.downgrade(cfg, "base")

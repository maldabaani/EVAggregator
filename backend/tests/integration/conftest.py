"""Integration tests require the docker-compose services (Postgres/TimescaleDB,
Redis, NATS) per engineering standards. They're skipped automatically if the
migration DB isn't reachable, so `pytest` still passes in environments without
docker-compose running (e.g. a bare dev machine) — CI always has the services
up before this directory runs.
"""

from __future__ import annotations

import asyncio

import asyncpg
import pytest

from evagg.core.config import settings


def _migration_db_reachable() -> bool:
    async def _probe() -> bool:
        try:
            conn = await asyncpg.connect(settings.migration_database_url.replace("+asyncpg", ""))
        except (OSError, asyncpg.PostgresError):
            return False
        await conn.close()
        return True

    return asyncio.run(_probe())


def _timescaledb_extension_available() -> bool:
    async def _probe() -> bool:
        try:
            conn = await asyncpg.connect(settings.migration_database_url.replace("+asyncpg", ""))
        except (OSError, asyncpg.PostgresError):
            return False
        try:
            row = await conn.fetchrow(
                "SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb'"
            )
            return row is not None
        finally:
            await conn.close()

    return asyncio.run(_probe())


requires_postgres = pytest.mark.skipif(
    not _migration_db_reachable(), reason="Postgres not reachable — start docker-compose services"
)

# Migration head includes the Task 6.2 hypertable conversion, which needs the
# `timescaledb` extension. The docker-compose `timescale/timescaledb` image
# always has it; a bare `postgresql` install (e.g. a contributor's laptop, or
# the sandbox that wrote this suite) does not.
requires_timescaledb = pytest.mark.skipif(
    not (_migration_db_reachable() and _timescaledb_extension_available()),
    reason="timescaledb extension not available — use the docker-compose Postgres image",
)

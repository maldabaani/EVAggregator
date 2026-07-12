"""Integration tests require the docker-compose services (Postgres/TimescaleDB,
Redis, NATS) per engineering standards. They're skipped automatically if a
given service isn't reachable, so `pytest` still passes in environments
without docker-compose running (e.g. a bare dev machine) — CI always has the
services up before this directory runs.

Redis and NATS both have a native (no-Docker) install path via Ubuntu's own
package archive (`apt-get install redis-server nats-server`), so
`test_redis_real.py` and `test_nats_real.py` exercise the real production
adapters (`RedisRateLimiter`, `RedisCarbonCache`, `NatsEventBus`) whenever
those servers are reachable — including in the sandbox that wrote this
suite, not just in CI.

TimescaleDB is the one exception: it isn't in Ubuntu's archive at all, only
in Timescale's own apt repo and the `timescale/timescaledb` Docker image,
both of which this sandbox's network policy blocks (same policy that blocks
Docker Hub generally). `test_migrations.py`'s TimescaleDB-dependent cases
(hypertable conversion, continuous aggregates, retention) can only run for
real in CI, against the docker-compose service declared in
`.github/workflows/backend-ci.yml` — and that was worth it: real TimescaleDB
caught three migration bugs no amount of local testing against bare Postgres
could have (a transaction-block restriction on continuous aggregate
creation, and two rounds of RLS-vs-TimescaleDB-feature conflicts that ended
in dropping compression on RLS-protected tables entirely, since TimescaleDB
doesn't allow the two to coexist on the same hypertable at all).
"""

from __future__ import annotations

import asyncio

import asyncpg
import pytest
import redis.asyncio as redis_asyncio

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


def _redis_reachable() -> bool:
    async def _probe() -> bool:
        client = redis_asyncio.from_url(settings.redis_url, socket_connect_timeout=2)
        try:
            return await client.ping()
        except (OSError, redis_asyncio.RedisError):
            return False
        finally:
            await client.aclose()

    return asyncio.run(_probe())


requires_redis = pytest.mark.skipif(
    not _redis_reachable(), reason="Redis not reachable — start docker-compose services (or a local redis-server)"
)


def _nats_reachable() -> bool:
    async def _probe() -> bool:
        import nats

        try:
            nc = await nats.connect(settings.nats_url, connect_timeout=2)
        except Exception:
            return False
        await nc.close()
        return True

    return asyncio.run(_probe())


requires_nats = pytest.mark.skipif(
    not _nats_reachable(), reason="NATS not reachable — start docker-compose services (or a local nats-server -js)"
)

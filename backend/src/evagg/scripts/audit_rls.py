"""Task 4.1 — verifies every tenant-scoped table has an active RLS policy.

Run in CI right after migrations apply. A new tenant-scoped model that ships
without its RLS policy in the same migration should fail the build, not slip
through as a silent cross-tenant data leak.

The pure check (`find_tables_missing_rls`) takes plain dicts describing what
the database reports, so it's unit-testable without a live Postgres
connection; `audit()` is the thin IO layer that queries `pg_tables` /
`pg_policies` and hands the results to the pure check.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from evagg.models.base import TENANT_SCOPED_TABLES

# Global reference/lookup tables intentionally have no tenant_id and are
# exempt from tenant-isolation RLS (e.g. carbon zone provider mapping, shared
# across every tenant).
EXEMPT_TABLES: frozenset[str] = frozenset({"carbon_zone"})

# `organization` is the tenant root itself — it's isolated by its own `id`
# column rather than a `tenant_id` FK, so it's audited alongside the
# tenant_id-keyed tables but needs a different policy expression.
SELF_TENANT_TABLES: frozenset[str] = frozenset({"organization"})


def tables_requiring_rls() -> set[str]:
    return (set(TENANT_SCOPED_TABLES) | SELF_TENANT_TABLES) - EXEMPT_TABLES


def find_tables_missing_rls(
    rowsecurity_by_table: dict[str, bool], policy_count_by_table: dict[str, int]
) -> list[str]:
    """Returns the sorted list of tables that are missing RLS enablement or
    have zero policies attached, out of the full set that requires it."""
    missing = []
    for table in sorted(tables_requiring_rls()):
        if not rowsecurity_by_table.get(table, False):
            missing.append(table)
        elif policy_count_by_table.get(table, 0) == 0:
            missing.append(table)
    return missing


async def audit(connection: AsyncConnection) -> list[str]:
    rowsecurity_rows = await connection.execute(
        text("SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname = 'public'")
    )
    rowsecurity_by_table = {row.tablename: bool(row.rowsecurity) for row in rowsecurity_rows}

    policy_rows = await connection.execute(
        text(
            "SELECT tablename, count(*) AS cnt FROM pg_policies "
            "WHERE schemaname = 'public' GROUP BY tablename"
        )
    )
    policy_count_by_table = {row.tablename: row.cnt for row in policy_rows}

    return find_tables_missing_rls(rowsecurity_by_table, policy_count_by_table)


async def _main() -> int:
    from evagg.core.db import engine

    async with engine.connect() as connection:
        missing = await audit(connection)

    if missing:
        print(f"RLS audit FAILED — missing policy/enablement on: {', '.join(missing)}", file=sys.stderr)
        return 1
    print("RLS audit passed — every tenant-scoped table has an active policy.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))

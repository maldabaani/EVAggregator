"""row level security policies

Task 4.1 — Multi-Tenancy Isolation Framework.

Creates the two application DB roles (`evagg_app`, `evagg_superadmin`) and
enables + forces Row-Level Security on every tenant-scoped table, keyed on
`tenant_id` (or `id` for `organization`, which is the tenant root itself).
`FORCE ROW LEVEL SECURITY` means even the table owner is subject to the
policy — only a role with the `BYPASSRLS` attribute (`evagg_superadmin`) skips
it, and that role is never used by the standard app connection pool.

The policy expression uses `NULLIF(current_setting('app.current_tenant',
true), '')::uuid`: `current_setting(..., true)` returns NULL instead of
raising when unset, so a connection with no tenant context set matches zero
rows rather than every row — fail closed, not open.

This migration reads its table list from `evagg.scripts.audit_rls`, the same
module used by the CI audit script, so there is exactly one source of truth
for "which tables must have a tenant-isolation policy."

Runs *before* the TimescaleDB migration (8679657fe757), not after: enabling
RLS on `meter_value`/`status_log` while they're still plain tables avoids a
real TimescaleDB restriction — it refuses to enable RLS on a hypertable that
already has compression ("columnstore") turned on. Converting to a
hypertable and enabling compression afterward is unaffected by RLS already
being in place.

Revision ID: cb7ac4e49b9a
Revises: b77170234860
Create Date: 2026-07-11 12:06:06.705857

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

from evagg.scripts.audit_rls import SELF_TENANT_TABLES, tables_requiring_rls

# revision identifiers, used by Alembic.
revision: str = 'cb7ac4e49b9a'
down_revision: Union[str, None] = 'b77170234860'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_POLICY_NAME = "tenant_isolation"


def upgrade() -> None:
    bind = op.get_bind()

    bind.execute(
        text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'evagg_app') THEN
                    CREATE ROLE evagg_app NOLOGIN;
                END IF;
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'evagg_superadmin') THEN
                    CREATE ROLE evagg_superadmin NOLOGIN BYPASSRLS;
                END IF;
            END
            $$;
            """
        )
    )

    bind.execute(text("GRANT USAGE ON SCHEMA public TO evagg_app, evagg_superadmin"))
    bind.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO evagg_app"))
    bind.execute(text("GRANT ALL ON ALL TABLES IN SCHEMA public TO evagg_superadmin"))
    bind.execute(
        text("GRANT SELECT, USAGE ON ALL SEQUENCES IN SCHEMA public TO evagg_app, evagg_superadmin")
    )
    bind.execute(
        text(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO evagg_app"
        )
    )
    bind.execute(text("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO evagg_superadmin"))

    for table in sorted(tables_requiring_rls()):
        tenant_column = "id" if table in SELF_TENANT_TABLES else "tenant_id"
        bind.execute(text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
        bind.execute(text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
        bind.execute(
            text(
                f'CREATE POLICY {_POLICY_NAME} ON "{table}" '
                f"USING ({tenant_column} = NULLIF(current_setting('app.current_tenant', true), '')::uuid) "
                f"WITH CHECK ({tenant_column} = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"
            )
        )


def downgrade() -> None:
    bind = op.get_bind()

    for table in sorted(tables_requiring_rls()):
        bind.execute(text(f'DROP POLICY IF EXISTS {_POLICY_NAME} ON "{table}"'))
        bind.execute(text(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY'))
        bind.execute(text(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY'))

    bind.execute(text("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM evagg_app, evagg_superadmin"))
    bind.execute(text("REVOKE USAGE ON SCHEMA public FROM evagg_app, evagg_superadmin"))

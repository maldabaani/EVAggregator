"""timescale hypertables

Converts `meter_value` and `status_log` into TimescaleDB hypertables and adds
the `meter_value_hourly` continuous aggregate per Task 6.2:

- `meter_value_hourly` continuous aggregate: retained indefinitely (no
  retention policy attached), refreshed hourly, feeds Task 4.4 / Task 5.4
  rollups.
- Chunk interval starts at 1 day per the doc's own note to "tune after real
  volume data from Task 2.2's load test" — revisit once production write
  volume is known.
- Retention (also Task 6.2) is configured in a later migration,
  timescale_retention, *after* RLS is enabled — see that migration's
  docstring for why the ordering is split three ways, and why compression
  (originally also planned here) was dropped for these two tables entirely.

Runs *before* the RLS migration (cb7ac4e49b9a), not after: TimescaleDB
refuses to create a continuous aggregate on a hypertable that already has
row-level security enabled ("cannot create continuous aggregate on
hypertable with row security"). The continuous aggregate has to exist before
`meter_value` gets RLS turned on.

Revision ID: 8679657fe757
Revises: b77170234860
Create Date: 2026-07-11 12:06:06.247342

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = '8679657fe757'
down_revision: Union[str, None] = 'b77170234860'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_PLAIN_ROLLUP_QUERY = """
    SELECT
        tenant_id,
        charger_id,
        transaction_id,
        measurand,
        unit,
        date_trunc('hour', ts) AS bucket,
        avg(value) AS avg_value,
        max(value) AS max_value,
        min(value) AS min_value,
        count(*) AS sample_count
    FROM meter_value
    GROUP BY tenant_id, charger_id, transaction_id, measurand, unit, bucket
"""

# TimescaleDB continuous aggregates refuse plain `date_trunc()` — they
# require the query's bucketing expression to be its own `time_bucket()`
# function ("continuous aggregate view must include a valid time bucket
# function"), which only exists once the extension is loaded. The plain
# Postgres fallback view above keeps `date_trunc` since `time_bucket`
# isn't available there at all.
_CONTINUOUS_AGGREGATE_QUERY = """
    SELECT
        tenant_id,
        charger_id,
        transaction_id,
        measurand,
        unit,
        time_bucket(INTERVAL '1 hour', ts) AS bucket,
        avg(value) AS avg_value,
        max(value) AS max_value,
        min(value) AS min_value,
        count(*) AS sample_count
    FROM meter_value
    GROUP BY tenant_id, charger_id, transaction_id, measurand, unit, bucket
"""


def _timescaledb_available(bind) -> bool:
    """Testing-mode machines (this sandbox included) can't reach
    TimescaleDB's package repo, so the extension is never installed there —
    only a real deployment (or CI's docker-compose service) has it. Rather
    than hard-fail `alembic upgrade head` on every dev machine, detect
    availability and fall back to a plain Postgres table + a plain (not
    continuously-refreshed) view with the same name and shape. Functionally
    identical for reads; just not incrementally materialized or chunked."""
    return bind.execute(
        text("SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb'")
    ).first() is not None


def upgrade() -> None:
    bind = op.get_bind()

    if not _timescaledb_available(bind):
        op.execute(f"CREATE OR REPLACE VIEW meter_value_hourly AS {_PLAIN_ROLLUP_QUERY}")
        return

    bind.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))

    # `if_not_exists => TRUE` on every TimescaleDB call below: the
    # `autocommit_block()` further down commits whatever's run before it as
    # a side effect of leaving the wrapped transaction, so a run that fails
    # partway through (e.g. on the continuous aggregate step) can leave the
    # hypertable conversions permanently committed even though Alembic never
    # marks this migration as applied. Without idempotency, retrying
    # `alembic upgrade head` after exactly that kind of partial failure then
    # fails immediately with "table ... is already a hypertable" instead of
    # picking up where it left off.
    bind.execute(
        text(
            "SELECT create_hypertable('meter_value', 'ts', "
            "chunk_time_interval => INTERVAL '1 day', migrate_data => TRUE, if_not_exists => TRUE)"
        )
    )
    bind.execute(
        text(
            "SELECT create_hypertable('status_log', 'ts', "
            "chunk_time_interval => INTERVAL '1 day', migrate_data => TRUE, if_not_exists => TRUE)"
        )
    )

    # Continuous aggregate: hourly rollup of raw meter values, retained
    # indefinitely even after raw rows age out at 90 days.
    #
    # `CREATE MATERIALIZED VIEW ... WITH (timescaledb.continuous) AS ...`
    # populates itself immediately (the implicit `WITH DATA`), which
    # TimescaleDB refuses to do inside a transaction block — but Alembic
    # wraps every migration in one transaction by default. This only
    # surfaced once real TimescaleDB executed this migration for the first
    # time (CI's docker-compose service); a bare Postgres install skips the
    # whole migration via `requires_timescaledb` and never hits it.
    # `autocommit_block()` steps outside that transaction just for this
    # statement, then Alembic resumes a normal transaction afterward.
    with op.get_context().autocommit_block():
        op.execute(
            f"""
            CREATE MATERIALIZED VIEW IF NOT EXISTS meter_value_hourly
            WITH (timescaledb.continuous) AS
            {_CONTINUOUS_AGGREGATE_QUERY}
            """
        )
    bind.execute(
        text(
            "SELECT add_continuous_aggregate_policy('meter_value_hourly', "
            "start_offset => INTERVAL '3 hours', end_offset => INTERVAL '1 hour', "
            "schedule_interval => INTERVAL '1 hour', if_not_exists => TRUE)"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not _timescaledb_available(bind):
        op.execute("DROP VIEW IF EXISTS meter_value_hourly")
        return
    bind.execute(text("DROP MATERIALIZED VIEW IF EXISTS meter_value_hourly CASCADE"))

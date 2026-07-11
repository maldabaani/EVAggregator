"""timescale hypertables

Converts `meter_value` and `status_log` into TimescaleDB hypertables, adds the
`meter_value_hourly` continuous aggregate, and configures retention +
compression per Task 6.2:

- Raw meter values: 90-day retention, compressed after 7 days.
- `meter_value_hourly` continuous aggregate: retained indefinitely (no
  retention policy attached), refreshed hourly, feeds Task 4.4 / Task 5.4
  rollups.
- `status_log` gets the same retention/compression treatment as meter_value —
  the backlog doesn't call out a different policy for it, and it has similar
  unbounded-growth characteristics.
- Chunk interval starts at 1 day per the doc's own note to "tune after real
  volume data from Task 2.2's load test" — revisit once production write
  volume is known.

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


def upgrade() -> None:
    bind = op.get_bind()

    bind.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))

    bind.execute(
        text(
            "SELECT create_hypertable('meter_value', 'ts', "
            "chunk_time_interval => INTERVAL '1 day', migrate_data => TRUE)"
        )
    )
    bind.execute(
        text(
            "SELECT create_hypertable('status_log', 'ts', "
            "chunk_time_interval => INTERVAL '1 day', migrate_data => TRUE)"
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
            """
            CREATE MATERIALIZED VIEW meter_value_hourly
            WITH (timescaledb.continuous) AS
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
        )
    bind.execute(
        text(
            "SELECT add_continuous_aggregate_policy('meter_value_hourly', "
            "start_offset => INTERVAL '3 hours', end_offset => INTERVAL '1 hour', "
            "schedule_interval => INTERVAL '1 hour')"
        )
    )

    # Retention: drop raw rows past 90 days (the continuous aggregate above is
    # untouched by this policy since it targets the hypertable, not the view).
    bind.execute(text("SELECT add_retention_policy('meter_value', INTERVAL '90 days')"))
    bind.execute(text("SELECT add_retention_policy('status_log', INTERVAL '90 days')"))

    # Compression: chunks older than 7 days, segmented by the columns most
    # queries filter on so compressed reads stay efficient.
    bind.execute(
        text(
            "ALTER TABLE meter_value SET ("
            "timescaledb.compress, "
            "timescaledb.compress_segmentby = 'tenant_id, charger_id', "
            "timescaledb.compress_orderby = 'ts DESC')"
        )
    )
    bind.execute(text("SELECT add_compression_policy('meter_value', INTERVAL '7 days')"))

    bind.execute(
        text(
            "ALTER TABLE status_log SET ("
            "timescaledb.compress, "
            "timescaledb.compress_segmentby = 'tenant_id, charger_id', "
            "timescaledb.compress_orderby = 'ts DESC')"
        )
    )
    bind.execute(text("SELECT add_compression_policy('status_log', INTERVAL '7 days')"))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("SELECT remove_compression_policy('status_log', if_exists => TRUE)"))
    bind.execute(text("SELECT remove_compression_policy('meter_value', if_exists => TRUE)"))
    bind.execute(text("SELECT remove_retention_policy('status_log', if_exists => TRUE)"))
    bind.execute(text("SELECT remove_retention_policy('meter_value', if_exists => TRUE)"))
    bind.execute(text("DROP MATERIALIZED VIEW IF EXISTS meter_value_hourly CASCADE"))

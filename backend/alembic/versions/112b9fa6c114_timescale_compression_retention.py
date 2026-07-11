"""timescale compression and retention

Task 6.2 (continued) — retention and compression for `meter_value` and
`status_log`:

- Raw meter values / status logs: 90-day retention, compressed after 7 days.
- Compression is segmented/ordered by the columns most queries filter on
  (`tenant_id, charger_id`, `ts DESC`) so compressed reads stay efficient.

Split out from the original timescale_hypertables migration (8679657fe757)
and moved to run *after* RLS (cb7ac4e49b9a), not before: TimescaleDB refuses
`ALTER TABLE ... ENABLE ROW LEVEL SECURITY` once a hypertable has compression
("columnstore") enabled, so compression has to come after RLS, not before —
while the continuous aggregate in 8679657fe757 has the opposite constraint
(it must be created before RLS). RLS is the one migration that can satisfy
both, sitting between this one and 8679657fe757. Retention policies have no
documented RLS interaction, but are grouped here with compression rather
than left in 8679657fe757 out of caution, since this ordering conflict was
only discoverable by running against a real TimescaleDB instance (this
sandbox has no local TimescaleDB to test other permutations against).

Revision ID: 112b9fa6c114
Revises: cb7ac4e49b9a
Create Date: 2026-07-11 15:16:00.000000

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = '112b9fa6c114'
down_revision: Union[str, None] = 'cb7ac4e49b9a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # Retention: drop raw rows past 90 days (the continuous aggregate from
    # 8679657fe757 is untouched by this policy since it targets the
    # hypertable, not the view).
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

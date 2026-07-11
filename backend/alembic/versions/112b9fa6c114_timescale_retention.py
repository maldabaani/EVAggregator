"""timescale retention

Task 6.2 (continued) — retention for `meter_value` and `status_log`: raw rows
are dropped after 90 days (the `meter_value_hourly` continuous aggregate
from 8679657fe757 is retained indefinitely and untouched by this policy,
since it targets the hypertable, not the view).

This migration originally also enabled compression on both tables. Real
TimescaleDB (via CI's docker-compose service — this sandbox has no local
TimescaleDB to test against) rejected that outright: "columnstore cannot be
used on table with row security". Unlike the two other RLS/TimescaleDB
conflicts fixed earlier in this chain (continuous aggregates and RLS have an
orderable conflict — one must be set up before the other), compression and
RLS are not just order-sensitive, they are mutually exclusive on the same
hypertable in TimescaleDB, full stop — no migration ordering fixes it.
Per-project decision: keep RLS (tenant isolation stays enforced on every
tenant-scoped table with no exceptions) and drop compression. Storage growth
on these two high-volume tables is bounded by the 90-day retention policy
alone rather than by compression.

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


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("SELECT remove_retention_policy('status_log', if_exists => TRUE)"))
    bind.execute(text("SELECT remove_retention_policy('meter_value', if_exists => TRUE)"))

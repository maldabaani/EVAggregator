"""core relational schema

Baseline schema for every OLTP table across all epics (tenancy, identity,
hardware, billing, roaming, ocpp operational state, carbon zone lookup,
rollups). Driven directly from `evagg.models` metadata, which is the reviewed
source of truth for columns/types/FKs/indexes — see Task 6.1.

Timescale hypertable conversion happens in the next migration (8679657fe757);
RLS policies are added in cb7ac4e49b9a (Task 4.1), kept as separate steps so
each is independently reviewable and revertible.

Revision ID: b77170234860
Revises:
Create Date: 2026-07-11 12:06:05.549606

"""
from typing import Sequence, Union

from alembic import op

# Import every model module so Base.metadata is fully populated before we
# create tables from it.
import evagg.models  # noqa: F401
from evagg.models.base import Base

# revision identifiers, used by Alembic.
revision: str = 'b77170234860'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, checkfirst=True)

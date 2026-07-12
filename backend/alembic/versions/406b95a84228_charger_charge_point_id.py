"""charger charge_point_id

Adds `charger.charge_point_id` — the OCPP charge-point identity string (the
WS path segment / Basic Auth username a real charger connects as), distinct
from `charger.id` (the internal UUID primary key everything else FKs
against). Every OCPP handler and `evagg.ocpp_gateway.ws_app` identifies a
charger by this string; nothing before this migration had a column for it —
discovered while building real repositories against it (`evagg.persistence`).

Backfilled from `id` for any pre-existing rows so the `NOT NULL UNIQUE`
constraint can be added in one step; there are no real chargers registered
this way yet in any environment this has shipped to.

Revision ID: 406b95a84228
Revises: 112b9fa6c114
Create Date: 2026-07-12 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '406b95a84228'
down_revision: Union[str, None] = '112b9fa6c114'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("charger", sa.Column("charge_point_id", sa.String(255), nullable=True))
    op.execute("UPDATE charger SET charge_point_id = id::text WHERE charge_point_id IS NULL")
    op.alter_column("charger", "charge_point_id", nullable=False)
    op.create_unique_constraint("uq_charger_charge_point_id", "charger", ["charge_point_id"])
    op.create_index("ix_charger_charge_point_id", "charger", ["charge_point_id"])


def downgrade() -> None:
    op.drop_index("ix_charger_charge_point_id", table_name="charger")
    op.drop_constraint("uq_charger_charge_point_id", "charger", type_="unique")
    op.drop_column("charger", "charge_point_id")

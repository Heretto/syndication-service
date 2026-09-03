"""add_unique_constraint_to_sync_records

Revision ID: b1c2d3e4f5a6
Revises: f3a1c2d4e5b6
Create Date: 2026-09-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "f3a1c2d4e5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("sync_records") as batch_op:
        batch_op.create_unique_constraint("uq_sync_record", ["sync_id", "source_uuid"])


def downgrade() -> None:
    with op.batch_alter_table("sync_records") as batch_op:
        batch_op.drop_constraint("uq_sync_record", type_="unique")

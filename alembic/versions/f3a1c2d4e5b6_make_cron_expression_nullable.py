"""make_cron_expression_nullable

Revision ID: f3a1c2d4e5b6
Revises: a3f91b2c4e05
Create Date: 2026-09-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f3a1c2d4e5b6'
down_revision: Union[str, None] = 'a3f91b2c4e05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite requires batch mode to alter column nullability
    with op.batch_alter_table('syncs') as batch_op:
        batch_op.alter_column(
            'cron_expression',
            existing_type=sa.String(length=128),
            nullable=True,
        )


def downgrade() -> None:
    # Rows with NULL cron_expression must be given a value before restoring NOT NULL
    op.execute("UPDATE syncs SET cron_expression = '0 9 * * *' WHERE cron_expression IS NULL")
    with op.batch_alter_table('syncs') as batch_op:
        batch_op.alter_column(
            'cron_expression',
            existing_type=sa.String(length=128),
            nullable=False,
        )

"""add_warning_messages_to_sync_runs

Revision ID: a3f91b2c4e05
Revises: c97ce7702913
Create Date: 2026-08-25 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a3f91b2c4e05'
down_revision: Union[str, None] = 'c97ce7702913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('sync_runs', sa.Column('warning_messages', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('sync_runs', 'warning_messages')

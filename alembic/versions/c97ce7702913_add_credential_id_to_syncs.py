"""add_credential_id_to_syncs

Revision ID: c97ce7702913
Revises: ed00f753db49
Create Date: 2026-07-16 13:55:18.703780

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c97ce7702913'
down_revision: Union[str, Sequence[str], None] = 'ed00f753db49'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('syncs', sa.Column('credential_id', sa.String(length=36), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('syncs', 'credential_id')

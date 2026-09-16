"""add processed_count and total_count to sync_runs

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-09-16
"""
from alembic import op
import sqlalchemy as sa

revision = 'e4f5a6b7c8d9'
down_revision = 'd3e4f5a6b7c8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('sync_runs', sa.Column('processed_count', sa.Integer(), nullable=True))
    op.add_column('sync_runs', sa.Column('total_count', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('sync_runs', 'total_count')
    op.drop_column('sync_runs', 'processed_count')

"""Add deploy_audience column to syncs table.

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-08-25 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "d3e4f5a6b7c8"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("syncs", sa.Column("deploy_audience", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("syncs", "deploy_audience")

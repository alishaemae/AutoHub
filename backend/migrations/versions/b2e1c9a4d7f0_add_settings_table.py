"""add settings table

Revision ID: b2e1c9a4d7f0
Revises: 774a478136c0
Create Date: 2026-07-13 12:40:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'b2e1c9a4d7f0'
down_revision = '774a478136c0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'settings',
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('value', sa.Text(), nullable=False, server_default=''),
        sa.PrimaryKeyConstraint('key'),
    )


def downgrade():
    op.drop_table('settings')

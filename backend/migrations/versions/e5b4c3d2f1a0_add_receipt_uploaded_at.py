"""add receipt_uploaded_at to car_documents

Revision ID: e5b4c3d2f1a0
Revises: d4a3b2c1e6f2
Create Date: 2026-07-15 15:30:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'e5b4c3d2f1a0'
down_revision = 'd4a3b2c1e6f2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('car_documents',
                  sa.Column('receipt_uploaded_at', sa.DateTime(timezone=True),
                            nullable=True))


def downgrade():
    op.drop_column('car_documents', 'receipt_uploaded_at')

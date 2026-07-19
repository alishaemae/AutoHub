"""add doc_number and doc_date to signable_documents

Revision ID: c3f2a1b8e5d1
Revises: b2e1c9a4d7f0
Create Date: 2026-07-13 13:10:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'c3f2a1b8e5d1'
down_revision = 'b2e1c9a4d7f0'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('signable_documents',
                  sa.Column('doc_number', sa.String(length=32), nullable=False,
                            server_default=''))
    op.add_column('signable_documents',
                  sa.Column('doc_date', sa.String(length=32), nullable=False,
                            server_default=''))


def downgrade():
    op.drop_column('signable_documents', 'doc_date')
    op.drop_column('signable_documents', 'doc_number')

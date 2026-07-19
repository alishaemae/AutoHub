"""add receipt fields to car_documents and deposit_receipts table

Revision ID: d4a3b2c1e6f2
Revises: c3f2a1b8e5d1
Create Date: 2026-07-14 16:50:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'd4a3b2c1e6f2'
down_revision = 'c3f2a1b8e5d1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('cars',
                  sa.Column('ship_arrival_date', sa.String(length=32),
                            nullable=False, server_default=''))
    op.add_column('car_documents',
                  sa.Column('receipt_path', sa.String(length=512), nullable=False,
                            server_default=''))
    op.add_column('car_documents',
                  sa.Column('receipt_name', sa.String(length=255), nullable=False,
                            server_default=''))
    op.create_table(
        'deposit_receipts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('file_path', sa.String(length=512), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_deposit_receipts_user_id'), 'deposit_receipts',
                    ['user_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_deposit_receipts_user_id'), table_name='deposit_receipts')
    op.drop_table('deposit_receipts')
    op.drop_column('car_documents', 'receipt_name')
    op.drop_column('car_documents', 'receipt_path')
    op.drop_column('cars', 'ship_arrival_date')

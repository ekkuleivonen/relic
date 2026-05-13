"""create maintenance events table

Creates the internal cold-path event log. Autogenerate also reports the
existing ``files.meta`` expression indexes as model drift; they are real search
indexes and this migration deliberately leaves them untouched.

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-13 13:59:17.317934
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0015'
down_revision: str | Sequence[str] | None = '0014'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'maintenance_events',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('job', sa.String(length=128), nullable=False),
        sa.Column('action', sa.String(length=128), nullable=False),
        sa.Column('status', sa.String(length=64), nullable=False),
        sa.Column('batch_id', sa.Uuid(), nullable=False),
        sa.Column('bucket_id', sa.Uuid(), nullable=True),
        sa.Column('blob_id', sa.Uuid(), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column(
            'meta',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['bucket_id'], ['buckets.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_maintenance_events_action_created_at',
        'maintenance_events',
        ['action', 'created_at'],
        unique=False,
    )
    op.create_index(
        'ix_maintenance_events_batch_id_created_at',
        'maintenance_events',
        ['batch_id', 'created_at'],
        unique=False,
    )
    op.create_index(
        'ix_maintenance_events_blob_id_created_at',
        'maintenance_events',
        ['blob_id', 'created_at'],
        unique=False,
    )
    op.create_index(
        'ix_maintenance_events_bucket_id_created_at',
        'maintenance_events',
        ['bucket_id', 'created_at'],
        unique=False,
    )
    op.create_index(
        'ix_maintenance_events_job_created_at',
        'maintenance_events',
        ['job', 'created_at'],
        unique=False,
    )
    op.create_index(
        'ix_maintenance_events_status_created_at',
        'maintenance_events',
        ['status', 'created_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_maintenance_events_status_created_at', table_name='maintenance_events')
    op.drop_index('ix_maintenance_events_job_created_at', table_name='maintenance_events')
    op.drop_index('ix_maintenance_events_bucket_id_created_at', table_name='maintenance_events')
    op.drop_index('ix_maintenance_events_blob_id_created_at', table_name='maintenance_events')
    op.drop_index('ix_maintenance_events_batch_id_created_at', table_name='maintenance_events')
    op.drop_index('ix_maintenance_events_action_created_at', table_name='maintenance_events')
    op.drop_table('maintenance_events')

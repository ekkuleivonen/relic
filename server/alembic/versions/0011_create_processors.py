"""create processors

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-13 12:05:12.357199
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0011'
down_revision: str | Sequence[str] | None = '0010'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'processors',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('kind', sa.String(length=64), nullable=False),
        sa.Column(
            'enabled', sa.Boolean(), server_default=sa.text('true'), nullable=False
        ),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column(
            'subscribed_event_types',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            nullable=False,
        ),
        sa.Column(
            'config',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            nullable=False,
        ),
        sa.Column(
            'last_committed_offset',
            sa.BigInteger().with_variant(sa.Integer(), 'sqlite'),
            server_default=sa.text('0'),
            nullable=False,
        ),
        sa.Column('last_committed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_index('ix_processors_enabled', 'processors', ['enabled'], unique=False)
    op.create_index('ix_processors_kind', 'processors', ['kind'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_processors_kind', table_name='processors')
    op.drop_index('ix_processors_enabled', table_name='processors')
    op.drop_table('processors')

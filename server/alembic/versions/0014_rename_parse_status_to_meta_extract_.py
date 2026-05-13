"""rename parse_status to meta_extract_status

Renames ``files.parse_status`` -> ``files.meta_extract_status`` to align the
denormalized per-file status column with the substrate that writes it. The
column semantics are unchanged: 1=pending, 2=in_progress, 3=completed,
4=failed.

This migration deliberately does NOT touch the ``files.meta`` search indexes
(``ix_files_meta_*``) that autogenerate flags. They exist in the DB but the
model never declared them; that drift is tracked separately in the roadmap.

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-13 13:39:20.373787
"""

from collections.abc import Sequence

from alembic import op


revision: str = '0014'
down_revision: str | Sequence[str] | None = '0013'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        'files',
        'parse_status',
        new_column_name='meta_extract_status',
    )


def downgrade() -> None:
    op.alter_column(
        'files',
        'meta_extract_status',
        new_column_name='parse_status',
    )

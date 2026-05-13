"""drop legacy audit event id columns

Drops ``audit_events.file_ids``, ``audit_events.folder_ids``, and
``audit_events.blob_ids``. Resource-side ids that were stored in these columns
now live in the per-event ``metadata`` payload — the audit table envelope is
narrowed to "who did what" and the resource surfacing is the job of
``file_events`` and ``maintenance_events``.

This migration deliberately does NOT touch ``files.meta`` search indexes
(``ix_files_meta_extension``, ``ix_files_meta_keywords``,
``ix_files_meta_mimetype``, ``ix_files_meta_tags``) even though autogenerate
flags them as drift. Those indexes are real and used by file search; the
drift is that the model never declared them. A follow-up migration will
reconcile the model.

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-13 13:33:44.515710
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0013'
down_revision: str | Sequence[str] | None = '0012'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column('audit_events', 'folder_ids')
    op.drop_column('audit_events', 'blob_ids')
    op.drop_column('audit_events', 'file_ids')


def downgrade() -> None:
    op.add_column(
        'audit_events',
        sa.Column(
            'file_ids',
            postgresql.JSONB(astext_type=sa.Text()),
            autoincrement=False,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        'audit_events',
        sa.Column(
            'blob_ids',
            postgresql.JSONB(astext_type=sa.Text()),
            autoincrement=False,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        'audit_events',
        sa.Column(
            'folder_ids',
            postgresql.JSONB(astext_type=sa.Text()),
            autoincrement=False,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

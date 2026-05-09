"""file meta search indexes

Hand-written migration: alembic autogenerate cannot produce functional GIN
indexes with ``jsonb_path_ops`` over JSONB paths, so we declare them here
directly. Indexes are postgres-only; SQLite (used in tests) skips them.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-10 03:00:00.000000
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_files_meta_tags "
        "ON files USING GIN ((meta -> 'tags') jsonb_path_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_files_meta_keywords "
        "ON files USING GIN ((meta -> 'keywords') jsonb_path_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_files_meta_mimetype "
        "ON files ((meta ->> 'mimetype'))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_files_meta_extension "
        "ON files ((meta ->> 'extension'))"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("DROP INDEX IF EXISTS ix_files_meta_extension")
    op.execute("DROP INDEX IF EXISTS ix_files_meta_mimetype")
    op.execute("DROP INDEX IF EXISTS ix_files_meta_keywords")
    op.execute("DROP INDEX IF EXISTS ix_files_meta_tags")

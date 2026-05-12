"""blobs partial unique content_hash when refcount active

Revision ID: 0006
Revises: 0005

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_constraint("blobs_content_hash_key", "blobs", type_="unique")

    op.create_index(
        "uq_blobs_content_hash_live",
        "blobs",
        ["content_hash"],
        unique=True,
        postgresql_where=text("refcount > 0"),
        sqlite_where=sa.text("refcount > 0"),
    )


def downgrade() -> None:
    op.drop_index("uq_blobs_content_hash_live", table_name="blobs")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_unique_constraint(
            "blobs_content_hash_key", "blobs", ["content_hash"]
        )

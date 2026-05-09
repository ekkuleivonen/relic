"""folder min_tier nullable for inherit

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "folders",
        "min_tier",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "folders",
        "min_tier",
        existing_type=sa.Integer(),
        nullable=False,
    )

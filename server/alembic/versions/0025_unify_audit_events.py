"""unify_audit_events

Recreates ``audit_events`` with maintenance columns, migrates rows from
``maintenance_events`` (``action`` -> ``operation``), then drops the old table.

Revision ID: 0025
Revises: 0024
Create Date: 2026-05-20 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0025"
down_revision: str | Sequence[str] | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("operation", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.String(length=255), nullable=True),
        sa.Column("job", sa.String(length=128), nullable=True),
        sa.Column("batch_id", sa.Uuid(), nullable=True),
        sa.Column("bucket_id", sa.Uuid(), nullable=True),
        sa.Column("blob_id", sa.Uuid(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("meta", JSONType, nullable=False),
        sa.CheckConstraint(
            "status IN ('succeeded', 'failed', 'skipped')",
            name="ck_audit_events_status",
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["bucket_id"], ["buckets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_events_operation_created_at",
        "audit_events",
        ["operation", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_status_created_at",
        "audit_events",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_actor_id_created_at",
        "audit_events",
        ["actor_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_request_id",
        "audit_events",
        ["request_id"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_created_at_id",
        "audit_events",
        ["created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_job_created_at",
        "audit_events",
        ["job", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_batch_id_created_at",
        "audit_events",
        ["batch_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_bucket_id_created_at",
        "audit_events",
        ["bucket_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_blob_id_created_at",
        "audit_events",
        ["blob_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_audit_events_actor_id"),
        "audit_events",
        ["actor_id"],
        unique=False,
    )

    op.execute(
        """
        INSERT INTO audit_events (
            id,
            created_at,
            updated_at,
            operation,
            status,
            job,
            batch_id,
            bucket_id,
            blob_id,
            duration_ms,
            meta
        )
        SELECT
            id,
            created_at,
            created_at,
            action,
            status,
            job,
            batch_id,
            bucket_id,
            blob_id,
            duration_ms,
            meta
        FROM maintenance_events
        """
    )

    op.drop_index(
        "ix_maintenance_events_status_created_at", table_name="maintenance_events"
    )
    op.drop_index(
        "ix_maintenance_events_job_created_at", table_name="maintenance_events"
    )
    op.drop_index(
        "ix_maintenance_events_bucket_id_created_at", table_name="maintenance_events"
    )
    op.drop_index(
        "ix_maintenance_events_blob_id_created_at", table_name="maintenance_events"
    )
    op.drop_index(
        "ix_maintenance_events_batch_id_created_at", table_name="maintenance_events"
    )
    op.drop_index(
        "ix_maintenance_events_action_created_at", table_name="maintenance_events"
    )
    op.drop_table("maintenance_events")


def downgrade() -> None:
    op.create_table(
        "maintenance_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("job", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("bucket_id", sa.Uuid(), nullable=True),
        sa.Column("blob_id", sa.Uuid(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("meta", JSONType, nullable=False),
        sa.CheckConstraint(
            "status IN ('succeeded', 'failed', 'skipped')",
            name="ck_maintenance_events_status",
        ),
        sa.ForeignKeyConstraint(["bucket_id"], ["buckets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_maintenance_events_action_created_at",
        "maintenance_events",
        ["action", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_events_batch_id_created_at",
        "maintenance_events",
        ["batch_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_events_blob_id_created_at",
        "maintenance_events",
        ["blob_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_events_bucket_id_created_at",
        "maintenance_events",
        ["bucket_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_events_job_created_at",
        "maintenance_events",
        ["job", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_events_status_created_at",
        "maintenance_events",
        ["status", "created_at"],
        unique=False,
    )

    op.execute(
        """
        INSERT INTO maintenance_events (
            id,
            created_at,
            job,
            action,
            status,
            batch_id,
            bucket_id,
            blob_id,
            duration_ms,
            meta
        )
        SELECT
            id,
            created_at,
            job,
            operation,
            status,
            batch_id,
            bucket_id,
            blob_id,
            duration_ms,
            meta
        FROM audit_events
        WHERE job IS NOT NULL
        """
    )

    op.drop_index(op.f("ix_audit_events_actor_id"), table_name="audit_events")
    op.drop_index("ix_audit_events_blob_id_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_bucket_id_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_batch_id_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_job_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_created_at_id", table_name="audit_events")
    op.drop_index("ix_audit_events_request_id", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_id_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_status_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_operation_created_at", table_name="audit_events")
    op.drop_table("audit_events")

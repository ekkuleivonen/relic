"""rename_buckets_to_storage_backends

Revision ID: 0027
Revises: 0026
Create Date: 2026-05-20 14:24:29.098484
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0027"
down_revision: str | Sequence[str] | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.rename_table("buckets", "storage_backends")
    with op.batch_alter_table("storage_backends") as batch_op:
        batch_op.alter_column("bucket", new_column_name="namespace")
        batch_op.alter_column("storage_kind", new_column_name="kind")

    op.rename_table("bucket_probes", "storage_backend_probes")
    op.drop_index("ix_bucket_probes_bucket_id_observed_at", table_name="storage_backend_probes")
    op.drop_index("ix_bucket_probes_observed_at", table_name="storage_backend_probes")
    with op.batch_alter_table("storage_backend_probes") as batch_op:
        batch_op.alter_column("bucket_id", new_column_name="storage_backend_id")
    op.create_index(
        "ix_storage_backend_probes_storage_backend_id_observed_at",
        "storage_backend_probes",
        ["storage_backend_id", "observed_at"],
        unique=False,
    )
    op.create_index(
        "ix_storage_backend_probes_observed_at",
        "storage_backend_probes",
        ["observed_at"],
        unique=False,
    )

    op.drop_index("ix_audit_events_bucket_id_created_at", table_name="audit_events")
    with op.batch_alter_table("audit_events") as batch_op:
        batch_op.alter_column("bucket_id", new_column_name="storage_backend_id")
    op.create_index(
        "ix_audit_events_storage_backend_id_created_at",
        "audit_events",
        ["storage_backend_id", "created_at"],
        unique=False,
    )

    op.drop_index("ix_blobs_bucket_id", table_name="blobs")
    with op.batch_alter_table("blobs") as batch_op:
        batch_op.alter_column("bucket_id", new_column_name="storage_backend_id")
    op.create_index(
        op.f("ix_blobs_storage_backend_id"),
        "blobs",
        ["storage_backend_id"],
        unique=False,
    )

    with op.batch_alter_table("folders") as batch_op:
        batch_op.alter_column(
            "preferred_bucket_id", new_column_name="preferred_storage_backend_id"
        )

    with op.batch_alter_table("multipart_uploads") as batch_op:
        batch_op.alter_column(
            "storage_bucket_id", new_column_name="storage_backend_id"
        )


def downgrade() -> None:
    with op.batch_alter_table("multipart_uploads") as batch_op:
        batch_op.alter_column(
            "storage_backend_id", new_column_name="storage_bucket_id"
        )

    with op.batch_alter_table("folders") as batch_op:
        batch_op.alter_column(
            "preferred_storage_backend_id", new_column_name="preferred_bucket_id"
        )

    op.drop_index(op.f("ix_blobs_storage_backend_id"), table_name="blobs")
    with op.batch_alter_table("blobs") as batch_op:
        batch_op.alter_column("storage_backend_id", new_column_name="bucket_id")
    op.create_index("ix_blobs_bucket_id", "blobs", ["bucket_id"], unique=False)

    op.drop_index(
        "ix_audit_events_storage_backend_id_created_at", table_name="audit_events"
    )
    with op.batch_alter_table("audit_events") as batch_op:
        batch_op.alter_column("storage_backend_id", new_column_name="bucket_id")
    op.create_index(
        "ix_audit_events_bucket_id_created_at",
        "audit_events",
        ["bucket_id", "created_at"],
        unique=False,
    )

    op.drop_index(
        "ix_storage_backend_probes_storage_backend_id_observed_at",
        table_name="storage_backend_probes",
    )
    op.drop_index(
        "ix_storage_backend_probes_observed_at", table_name="storage_backend_probes"
    )
    with op.batch_alter_table("storage_backend_probes") as batch_op:
        batch_op.alter_column("storage_backend_id", new_column_name="bucket_id")
    op.create_index(
        "ix_bucket_probes_bucket_id_observed_at",
        "storage_backend_probes",
        ["bucket_id", "observed_at"],
        unique=False,
    )
    op.create_index(
        "ix_bucket_probes_observed_at",
        "storage_backend_probes",
        ["observed_at"],
        unique=False,
    )
    op.rename_table("storage_backend_probes", "bucket_probes")

    with op.batch_alter_table("storage_backends") as batch_op:
        batch_op.alter_column("kind", new_column_name="storage_kind")
        batch_op.alter_column("namespace", new_column_name="bucket")
    op.rename_table("storage_backends", "buckets")

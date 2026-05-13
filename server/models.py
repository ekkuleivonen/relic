import datetime as dt
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON
from constants import META_EXTRACT_STATUS_PENDING, PROCESSOR_SOURCE_ADMIN
from utils.crypto import decrypt_string, encrypt_string

JSONType = JSON().with_variant(JSONB, "postgresql")
GUID = Uuid

class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    access_keys: Mapped[list["AccessKey"]] = relationship(back_populates="user")


class AccessKey(Base, TimestampMixin):
    __tablename__ = "access_keys"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    _secret_access_key: Mapped[str] = mapped_column(
        "secret_access_key", Text, nullable=False
    )
    last_used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="access_keys")

    @property
    def secret_access_key(self) -> str:
        return decrypt_string(self._secret_access_key)

    @secret_access_key.setter
    def secret_access_key(self, value: str) -> None:
        self._secret_access_key = encrypt_string(value)


class Bucket(Base, TimestampMixin):
    __tablename__ = "buckets"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    region: Mapped[str] = mapped_column(String(128), nullable=False)
    bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    _key_id: Mapped[str] = mapped_column("key_id", Text, nullable=False)
    _secret_access_key: Mapped[str] = mapped_column(
        "secret_access_key", Text, nullable=False
    )
    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    max_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    probe_latency_put_ms: Mapped[int | None] = mapped_column(Integer)
    probe_latency_head_ms: Mapped[int | None] = mapped_column(Integer)
    probe_latency_get_ms: Mapped[int | None] = mapped_column(Integer)
    probe_latency_delete_ms: Mapped[int | None] = mapped_column(Integer)

    blobs: Mapped[list["Blob"]] = relationship(back_populates="bucket")

    @property
    def key_id(self) -> str:
        return decrypt_string(self._key_id)

    @key_id.setter
    def key_id(self, value: str) -> None:
        self._key_id = encrypt_string(value)

    @property
    def secret_access_key(self) -> str:
        return decrypt_string(self._secret_access_key)

    @secret_access_key.setter
    def secret_access_key(self, value: str) -> None:
        self._secret_access_key = encrypt_string(value)


class Blob(Base, TimestampMixin):
    __tablename__ = "blobs"
    __table_args__ = (
        Index(
            "uq_blobs_content_hash_live",
            "content_hash",
            unique=True,
            postgresql_where=text("refcount > 0"),
            sqlite_where=text("refcount > 0"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    bucket_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("buckets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    bucket_key: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    refcount: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    accessed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    bucket: Mapped[Bucket] = relationship(back_populates="blobs")
    files: Mapped[list["File"]] = relationship(back_populates="blob")


class Folder(Base, TimestampMixin):
    __tablename__ = "folders"
    __table_args__ = (
        UniqueConstraint("parent_id", "name", name="uq_folders_parent_name"),
        Index(
            "uq_folders_single_root",
            text("(parent_id IS NULL)"),
            unique=True,
            postgresql_where=text("parent_id IS NULL"),
            sqlite_where=text("parent_id IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("folders.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    cooldown_days: Mapped[int | None] = mapped_column(Integer)
    # NULL = inherit from parent (root should still set an explicit tier in practice).
    min_tier: Mapped[int | None] = mapped_column(Integer, nullable=True)

    parent: Mapped["Folder | None"] = relationship(
        remote_side=[id], back_populates="children"
    )
    children: Mapped[list["Folder"]] = relationship(back_populates="parent")
    files: Mapped[list["File"]] = relationship(back_populates="folder")


class FolderAccess(Base, TimestampMixin):
    __tablename__ = "folder_access"
    __table_args__ = (
        UniqueConstraint("user_id", "folder_id", name="uq_folder_access_user_folder"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    folder_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("folders.id", ondelete="CASCADE"), nullable=False
    )
    permissions: Mapped[int] = mapped_column(Integer, nullable=False)


class File(Base, TimestampMixin):
    __tablename__ = "files"
    __table_args__ = (
        UniqueConstraint("folder_id", "name", name="uq_files_folder_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    folder_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("folders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    blob_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("blobs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Status of the latest meta_extract substrate run on this file. The column
    # is denormalized — file_events.processor.meta_extract.{completed,failed}
    # is the source of truth for processor outcomes. We keep this here so the
    # filesystem UI can render per-file badges without a per-row event lookup.
    meta_extract_status: Mapped[int] = mapped_column(
        Integer, nullable=False, default=META_EXTRACT_STATUS_PENDING
    )
    meta: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)

    folder: Mapped[Folder] = relationship(back_populates="files")
    blob: Mapped[Blob] = relationship(back_populates="files")
    uploader: Mapped[User] = relationship()

    @property
    def uploaded_by_name(self) -> str | None:
        return self.uploader.name if self.uploader else None


class MultipartUpload(Base, TimestampMixin):
    __tablename__ = "multipart_uploads"
    __table_args__ = (
        Index("ix_multipart_uploads_uploaded_by_created_at", "uploaded_by", "created_at"),
        Index("ix_multipart_uploads_bucket_key", "bucket_name", "object_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    bucket_name: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    folder_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("folders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    storage_bucket_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("buckets.id", ondelete="RESTRICT"), nullable=False
    )
    meta: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)

    folder: Mapped[Folder] = relationship()
    user: Mapped[User] = relationship()
    storage_bucket: Mapped[Bucket] = relationship()
    parts: Mapped[list["MultipartUploadPart"]] = relationship(
        back_populates="upload",
        cascade="all, delete-orphan",
        order_by="MultipartUploadPart.part_number",
    )


class MultipartUploadPart(Base, TimestampMixin):
    __tablename__ = "multipart_upload_parts"
    __table_args__ = (
        UniqueConstraint(
            "upload_id",
            "part_number",
            name="uq_multipart_upload_parts_upload_part_number",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    upload_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("multipart_uploads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    part_number: Mapped[int] = mapped_column(Integer, nullable=False)
    bucket_key: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    etag: Mapped[str] = mapped_column(String(64), nullable=False)

    upload: Mapped[MultipartUpload] = relationship(back_populates="parts")


class AuditEvent(Base, TimestampMixin):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_created_at_id", "created_at", "id"),
        Index("ix_audit_events_operation_created_at", "operation", "created_at"),
        Index("ix_audit_events_status_created_at", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    operation: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    request_id: Mapped[str | None] = mapped_column(String(255), index=True)
    meta: Mapped[dict] = mapped_column(
        "metadata", JSONType, nullable=False, default=dict
    )

    actor: Mapped[User | None] = relationship()


class FileEvent(Base):
    __tablename__ = "file_events"
    __table_args__ = (
        Index("ix_file_events_offset", "offset", unique=True),
        Index("ix_file_events_event_type_created_at", "event_type", "created_at"),
        Index("ix_file_events_status_created_at", "status", "created_at"),
        Index("ix_file_events_actor_user_id_created_at", "actor_user_id", "created_at"),
        Index("ix_file_events_request_id", "request_id"),
        Index("ix_file_events_file_id_created_at", "file_id", "created_at"),
        Index("ix_file_events_folder_id_created_at", "folder_id", "created_at"),
        Index(
            "uq_file_events_idempotency_key",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
            sqlite_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    offset: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        Identity(),
        nullable=False,
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(64), nullable=False, default="succeeded", server_default="succeeded"
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL")
    )
    request_id: Mapped[str | None] = mapped_column(String(255))
    idempotency_key: Mapped[str | None] = mapped_column(String(255))
    file_id: Mapped[uuid.UUID | None] = mapped_column(GUID())
    folder_id: Mapped[uuid.UUID | None] = mapped_column(GUID())
    payload: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)

    actor: Mapped[User | None] = relationship()


class MaintenanceEvent(Base):
    __tablename__ = "maintenance_events"
    __table_args__ = (
        Index("ix_maintenance_events_job_created_at", "job", "created_at"),
        Index("ix_maintenance_events_action_created_at", "action", "created_at"),
        Index("ix_maintenance_events_status_created_at", "status", "created_at"),
        Index("ix_maintenance_events_batch_id_created_at", "batch_id", "created_at"),
        Index("ix_maintenance_events_bucket_id_created_at", "bucket_id", "created_at"),
        Index("ix_maintenance_events_blob_id_created_at", "blob_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    job: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    batch_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    bucket_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("buckets.id", ondelete="SET NULL")
    )
    # Deliberately not a foreign key: cold-path rows may describe a blob that
    # has already been purged by the time an operator inspects the event.
    blob_id: Mapped[uuid.UUID | None] = mapped_column(GUID())
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    meta: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)

    bucket: Mapped[Bucket | None] = relationship()


class Processor(Base, TimestampMixin):
    """Configuration + cursor for a warm-path event consumer.

    Each row is one logical consumer of `file_events`. The dispatcher reads
    `last_committed_offset` to find new events to enqueue; the worker advances
    it after the substrate handler succeeds. See ROADMAP `Async Processors`
    for the full invariants.
    """

    __tablename__ = "processors"
    __table_args__ = (
        Index("ix_processors_kind", "kind"),
        Index("ix_processors_enabled", "enabled"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, default=PROCESSOR_SOURCE_ADMIN
    )
    subscribed_event_types: Mapped[list[str]] = mapped_column(
        JSONType, nullable=False, default=list
    )
    folder_scopes: Mapped[list[dict]] = mapped_column(
        JSONType, nullable=False, default=list, server_default=text("'[]'")
    )
    config: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    last_committed_offset: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    last_committed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    last_failed_event_id: Mapped[uuid.UUID | None] = mapped_column(GUID())
    last_failed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_class: Mapped[str | None] = mapped_column(String(255))
    last_error_message: Mapped[str | None] = mapped_column(Text)

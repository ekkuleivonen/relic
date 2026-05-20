import datetime as dt
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
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
from enums import EventStatus, Permission, StorageBackendKind, UserRole
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
    __table_args__ = (
        CheckConstraint(
            f"role IN ({','.join(str(int(role)) for role in UserRole)})",
            name="ck_users_role",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[int] = mapped_column(
        Integer, nullable=False, default=int(UserRole.USER)
    )

    access_keys: Mapped[list["AccessKey"]] = relationship(back_populates="user")


class AccessKey(Base, TimestampMixin):
    __tablename__ = "access_keys"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID] = mapped_column(
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


class StorageBackend(Base, TimestampMixin):
    __tablename__ = "storage_backends"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    region: Mapped[str] = mapped_column(String(128), nullable=False)
    namespace: Mapped[str] = mapped_column(String(255), nullable=False)
    _key_id: Mapped[str] = mapped_column("key_id", Text, nullable=False)
    _secret_access_key: Mapped[str] = mapped_column(
        "secret_access_key", Text, nullable=False
    )
    max_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kind: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=StorageBackendKind.S3,
        server_default=StorageBackendKind.S3,
    )

    blobs: Mapped[list["Blob"]] = relationship(back_populates="storage_backend")
    probes: Mapped[list["StorageBackendProbe"]] = relationship(
        back_populates="storage_backend",
        cascade="all, delete-orphan",
        order_by="desc(StorageBackendProbe.observed_at)",
    )

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


class StorageBackendProbe(Base):
    """Per-probe sample of storage backend reachability and per-op latency.

    Storage backends do not carry a static ``tier`` anymore; placement ranks them
    by averaging ``put/head/get/delete`` latency across the most recent successful
    probes (see :func:`infra.db.stores.placement.hotness_ranked_storage_backends`).
    """

    __tablename__ = "storage_backend_probes"
    __table_args__ = (
        Index(
            "ix_storage_backend_probes_storage_backend_id_observed_at",
            "storage_backend_id",
            "observed_at",
        ),
        Index("ix_storage_backend_probes_observed_at", "observed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    storage_backend_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("storage_backends.id", ondelete="CASCADE"), nullable=False
    )
    observed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    put_ms: Mapped[int | None] = mapped_column(Integer)
    head_ms: Mapped[int | None] = mapped_column(Integer)
    get_ms: Mapped[int | None] = mapped_column(Integer)
    delete_ms: Mapped[int | None] = mapped_column(Integer)

    storage_backend: Mapped[StorageBackend] = relationship(back_populates="probes")


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
    storage_backend_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("storage_backends.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    bucket_key: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mimetype: Mapped[str] = mapped_column(
        String(255), nullable=False, default="application/octet-stream"
    )
    extension: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    refcount: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    accessed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    # Wall-clock of the last successful migration between storage_backends. The
    # storage maintenance cron uses this to enforce a minimum residency window
    # before considering a blob for another move (anti-thrash hysteresis).
    migrated_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    storage_backend: Mapped[StorageBackend] = relationship(back_populates="blobs")
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
    # Optional power-user preference for which bucket new uploads under this
    # subtree land in. NULL = inherit from parent; root NULL = "use the hottest
    # available bucket". The maintenance cron may still demote files out of the
    # preferred bucket once it fills, but new uploads preferentially go there
    # whenever capacity allows.
    preferred_storage_backend_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("storage_backends.id", ondelete="SET NULL"),
        nullable=True,
    )

    parent: Mapped["Folder | None"] = relationship(
        remote_side=[id], back_populates="children"
    )
    children: Mapped[list["Folder"]] = relationship(back_populates="parent")
    files: Mapped[list["File"]] = relationship(back_populates="folder")
    preferred_storage_backend: Mapped[StorageBackend | None] = relationship()


class FolderAccess(Base, TimestampMixin):
    __tablename__ = "folder_access"
    __table_args__ = (
        CheckConstraint("permissions > 0", name="ck_folder_access_permissions_positive"),
        CheckConstraint(
            f"(permissions & ~{int(Permission.READ | Permission.WRITE | Permission.DELETE | Permission.ENRICH)}) = 0",
            name="ck_folder_access_permissions_known_bits",
        ),
        CheckConstraint(
            f"(permissions & {int(Permission.READ)}) != 0 OR permissions = 0",
            name="ck_folder_access_permissions_read_required",
        ),
        UniqueConstraint("actor_id", "folder_id", name="uq_folder_access_actor_folder"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID] = mapped_column(
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
    actor_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Opaque consumer-owned metadata; see ``domain.files.meta``.
    meta: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)

    folder: Mapped[Folder] = relationship(back_populates="files")
    blob: Mapped[Blob] = relationship(back_populates="files")
    actor: Mapped[User] = relationship()

    @property
    def actor_name(self) -> str | None:
        return self.actor.name if self.actor else None


class FilesystemEvent(Base):
    """Append-only integrator subscription log for file and folder lifecycle changes."""

    __tablename__ = "filesystem_events"
    __table_args__ = (
        Index("ix_filesystem_events_seq", "seq", unique=True),
        Index("ix_filesystem_events_folder_id_seq", "folder_id", "seq"),
        Index("ix_filesystem_events_file_id_seq", "file_id", "seq"),
        Index(
            "ix_filesystem_events_event_type_created_at",
            "event_type",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    seq: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        nullable=False,
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    folder_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    request_id: Mapped[str | None] = mapped_column(String(255))
    payload: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)


class MultipartUpload(Base, TimestampMixin):
    __tablename__ = "multipart_uploads"
    __table_args__ = (
        Index("ix_multipart_uploads_actor_id_created_at", "actor_id", "created_at"),
        Index("ix_multipart_uploads_bucket_key", "bucket_name", "object_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    bucket_name: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    folder_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("folders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    storage_backend_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("storage_backends.id", ondelete="RESTRICT"), nullable=False
    )
    meta: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)

    folder: Mapped[Folder] = relationship()
    actor: Mapped[User] = relationship()
    storage_backend: Mapped[StorageBackend] = relationship()
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
    """Unified audit log for actor-driven admin actions and storage maintenance."""

    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({','.join(repr(status.value) for status in (EventStatus.SUCCEEDED, EventStatus.FAILED, EventStatus.SKIPPED))})",
            name="ck_audit_events_status",
        ),
        Index("ix_audit_events_operation_created_at", "operation", "created_at"),
        Index("ix_audit_events_status_created_at", "status", "created_at"),
        Index("ix_audit_events_actor_id_created_at", "actor_id", "created_at"),
        Index("ix_audit_events_request_id", "request_id"),
        Index("ix_audit_events_created_at_id", "created_at", "id"),
        Index("ix_audit_events_job_created_at", "job", "created_at"),
        Index("ix_audit_events_batch_id_created_at", "batch_id", "created_at"),
        Index(
            "ix_audit_events_storage_backend_id_created_at",
            "storage_backend_id",
            "created_at",
        ),
        Index("ix_audit_events_blob_id_created_at", "blob_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    operation: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    request_id: Mapped[str | None] = mapped_column(String(255))
    job: Mapped[str | None] = mapped_column(String(128))
    batch_id: Mapped[uuid.UUID | None] = mapped_column(GUID())
    storage_backend_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("storage_backends.id", ondelete="SET NULL")
    )
    # Deliberately not a foreign key: maintenance rows may reference purged blobs.
    blob_id: Mapped[uuid.UUID | None] = mapped_column(GUID())
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    meta: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)

    actor: Mapped[User | None] = relationship()
    storage_backend: Mapped[StorageBackend | None] = relationship()

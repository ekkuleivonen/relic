import datetime as dt
import uuid

from sqlalchemy import (
    BigInteger,
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
from utils.crypto import decrypt_string, encrypt_string

JSONType = JSON().with_variant(JSONB, "postgresql")
GUID = Uuid

PARSE_STATUS_PENDING = 1
PARSE_STATUS_IN_PROGRESS = 2
PARSE_STATUS_COMPLETED = 3
PARSE_STATUS_FAILED = 4


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
    secret_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    last_used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="access_keys")


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
    parse_status: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    meta: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)

    folder: Mapped[Folder] = relationship(back_populates="files")
    blob: Mapped[Blob] = relationship(back_populates="files")
    uploader: Mapped[User] = relationship()

    @property
    def uploaded_by_name(self) -> str | None:
        return self.uploader.name if self.uploader else None


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
    # file_ids are legacy, can be dropped soonish
    file_ids: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    folder_ids: Mapped[list[str]] = mapped_column(
        JSONType, nullable=False, default=list
    )
    # blob_ids are legacy, can be dropped soonish i guess?
    blob_ids: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    meta: Mapped[dict] = mapped_column(
        "metadata", JSONType, nullable=False, default=dict
    )

    actor: Mapped[User | None] = relationship()

"""Emit file events from use cases (same transaction as the mutation)."""

from __future__ import annotations

import uuid

from application.uow import UnitOfWork
from domain.file_events.types import (
    FILE_EVENT_CONTENT_UPDATED,
    FILE_EVENT_CREATED,
    FILE_EVENT_DELETED,
    FILE_EVENT_META_UPDATED,
    FILE_EVENT_MOVED,
    FILE_EVENT_RENAMED,
)
from ports.entities import Blob, File


def _blob_fields(blob: Blob) -> dict:
    return {
        "blob_id": str(blob.id),
        "size_bytes": blob.size_bytes,
        "mimetype": blob.mimetype,
        "extension": blob.extension,
    }


def emit_file_created(
    uow: UnitOfWork,
    *,
    file: File,
    blob: Blob,
    origin: str,
    actor_id: uuid.UUID | None = None,
    request_id: str | None = None,
    source_file_id: uuid.UUID | None = None,
) -> None:
    payload = {
        "name": file.name,
        **_blob_fields(blob),
        "meta": dict(file.meta or {}),
        "origin": origin,
    }
    if source_file_id is not None:
        payload["source_file_id"] = str(source_file_id)
    uow.file_events.emit(
        event_type=FILE_EVENT_CREATED,
        file_id=file.id,
        folder_id=file.folder_id,
        actor_id=actor_id or file.actor_id,
        request_id=request_id,
        payload=payload,
    )


def emit_file_content_updated(
    uow: UnitOfWork,
    *,
    file: File,
    blob: Blob,
    previous_blob_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
    request_id: str | None = None,
) -> None:
    uow.file_events.emit(
        event_type=FILE_EVENT_CONTENT_UPDATED,
        file_id=file.id,
        folder_id=file.folder_id,
        actor_id=actor_id or file.actor_id,
        request_id=request_id,
        payload={
            "name": file.name,
            **_blob_fields(blob),
            "previous_blob_id": str(previous_blob_id),
            "meta": dict(file.meta or {}),
        },
    )


def emit_file_meta_updated(
    uow: UnitOfWork,
    *,
    file: File,
    blob: Blob,
    actor_id: uuid.UUID | None = None,
    request_id: str | None = None,
) -> None:
    uow.file_events.emit(
        event_type=FILE_EVENT_META_UPDATED,
        file_id=file.id,
        folder_id=file.folder_id,
        actor_id=actor_id or file.actor_id,
        request_id=request_id,
        payload={
            "name": file.name,
            "blob_id": str(blob.id),
            "meta": dict(file.meta or {}),
        },
    )


def emit_file_renamed(
    uow: UnitOfWork,
    *,
    file: File,
    blob: Blob,
    previous_name: str,
    actor_id: uuid.UUID | None = None,
    request_id: str | None = None,
) -> None:
    uow.file_events.emit(
        event_type=FILE_EVENT_RENAMED,
        file_id=file.id,
        folder_id=file.folder_id,
        actor_id=actor_id or file.actor_id,
        request_id=request_id,
        payload={
            "name": file.name,
            "previous_name": previous_name,
            "blob_id": str(blob.id),
        },
    )


def emit_file_moved(
    uow: UnitOfWork,
    *,
    file: File,
    blob: Blob,
    from_folder_id: uuid.UUID,
    previous_name: str,
    actor_id: uuid.UUID | None = None,
    request_id: str | None = None,
) -> None:
    uow.file_events.emit(
        event_type=FILE_EVENT_MOVED,
        file_id=file.id,
        folder_id=file.folder_id,
        actor_id=actor_id or file.actor_id,
        request_id=request_id,
        payload={
            "name": file.name,
            "previous_name": previous_name,
            "from_folder_id": str(from_folder_id),
            "to_folder_id": str(file.folder_id),
            "blob_id": str(blob.id),
        },
    )


def emit_file_deleted(
    uow: UnitOfWork,
    *,
    file: File,
    blob: Blob,
    actor_id: uuid.UUID | None = None,
    request_id: str | None = None,
) -> None:
    uow.file_events.emit(
        event_type=FILE_EVENT_DELETED,
        file_id=file.id,
        folder_id=file.folder_id,
        actor_id=actor_id,
        request_id=request_id,
        payload={
            "name": file.name,
            "blob_id": str(blob.id),
        },
    )

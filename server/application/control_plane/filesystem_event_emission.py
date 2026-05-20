"""Emit filesystem subscription events from use cases (same transaction as mutation)."""

from __future__ import annotations

import uuid

from application.uow import UnitOfWork
from domain.filesystem_events.types import (
    FILESYSTEM_EVENT_CONTENT_UPDATED,
    FILESYSTEM_EVENT_CREATED,
    FILESYSTEM_EVENT_DELETED,
    FILESYSTEM_EVENT_FOLDER_CREATED,
    FILESYSTEM_EVENT_FOLDER_DELETED,
    FILESYSTEM_EVENT_FOLDER_DUPLICATED,
    FILESYSTEM_EVENT_FOLDER_MOVED,
    FILESYSTEM_EVENT_FOLDER_RENAMED,
    FILESYSTEM_EVENT_META_UPDATED,
    FILESYSTEM_EVENT_MOVED,
    FILESYSTEM_EVENT_RENAMED,
)
from ports.entities import Blob, File, Folder


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
    uow.filesystem_events.emit(
        event_type=FILESYSTEM_EVENT_CREATED,
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
    uow.filesystem_events.emit(
        event_type=FILESYSTEM_EVENT_CONTENT_UPDATED,
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
    uow.filesystem_events.emit(
        event_type=FILESYSTEM_EVENT_META_UPDATED,
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
    uow.filesystem_events.emit(
        event_type=FILESYSTEM_EVENT_RENAMED,
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
    uow.filesystem_events.emit(
        event_type=FILESYSTEM_EVENT_MOVED,
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
    uow.filesystem_events.emit(
        event_type=FILESYSTEM_EVENT_DELETED,
        file_id=file.id,
        folder_id=file.folder_id,
        actor_id=actor_id,
        request_id=request_id,
        payload={
            "name": file.name,
            "blob_id": str(blob.id),
        },
    )


def emit_folder_created(
    uow: UnitOfWork,
    *,
    folder: Folder,
    actor_id: uuid.UUID | None = None,
    request_id: str | None = None,
) -> None:
    assert folder.parent_id is not None
    uow.filesystem_events.emit(
        event_type=FILESYSTEM_EVENT_FOLDER_CREATED,
        file_id=None,
        folder_id=folder.id,
        actor_id=actor_id,
        request_id=request_id,
        payload={
            "name": folder.name,
            "parent_id": str(folder.parent_id),
        },
    )


def emit_folder_renamed(
    uow: UnitOfWork,
    *,
    folder: Folder,
    previous_name: str,
    actor_id: uuid.UUID | None = None,
    request_id: str | None = None,
) -> None:
    assert folder.parent_id is not None
    uow.filesystem_events.emit(
        event_type=FILESYSTEM_EVENT_FOLDER_RENAMED,
        file_id=None,
        folder_id=folder.id,
        actor_id=actor_id,
        request_id=request_id,
        payload={
            "name": folder.name,
            "previous_name": previous_name,
            "parent_id": str(folder.parent_id),
        },
    )


def emit_folder_moved(
    uow: UnitOfWork,
    *,
    folder: Folder,
    from_parent_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
    request_id: str | None = None,
) -> None:
    assert folder.parent_id is not None
    uow.filesystem_events.emit(
        event_type=FILESYSTEM_EVENT_FOLDER_MOVED,
        file_id=None,
        folder_id=folder.parent_id,
        actor_id=actor_id,
        request_id=request_id,
        payload={
            "name": folder.name,
            "from_parent_id": str(from_parent_id),
            "to_parent_id": str(folder.parent_id),
        },
    )


def emit_folder_deleted(
    uow: UnitOfWork,
    *,
    folder: Folder,
    visibility_folder_id: uuid.UUID,
    recursive: bool,
    descendant_folder_count: int,
    file_count: int,
    actor_id: uuid.UUID | None = None,
    request_id: str | None = None,
) -> None:
    assert folder.parent_id is not None
    uow.filesystem_events.emit(
        event_type=FILESYSTEM_EVENT_FOLDER_DELETED,
        file_id=None,
        folder_id=visibility_folder_id,
        actor_id=actor_id,
        request_id=request_id,
        payload={
            "deleted_folder_id": str(folder.id),
            "name": folder.name,
            "parent_id": str(folder.parent_id),
            "recursive": recursive,
            "descendant_folder_count": descendant_folder_count,
            "file_count": file_count,
        },
    )


def emit_folder_duplicated(
    uow: UnitOfWork,
    *,
    folder: Folder,
    source_folder_id: uuid.UUID,
    destination_parent_id: uuid.UUID,
    recursive: bool,
    actor_id: uuid.UUID | None = None,
    request_id: str | None = None,
) -> None:
    uow.filesystem_events.emit(
        event_type=FILESYSTEM_EVENT_FOLDER_DUPLICATED,
        file_id=None,
        folder_id=folder.id,
        actor_id=actor_id,
        request_id=request_id,
        payload={
            "name": folder.name,
            "source_folder_id": str(source_folder_id),
            "destination_parent_id": str(destination_parent_id),
            "recursive": recursive,
        },
    )

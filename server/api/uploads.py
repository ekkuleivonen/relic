import datetime as dt
import uuid
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

import settings as S
from api.dependencies import CurrentUser
from database import DbSession
from managers.exceptions import BadRequestError
from schema_plan import Permission
from services import folder_access as folder_access_service
from services import events as event_service
from services import objects as object_service
from services import s3_signing

router = APIRouter()


class PresignUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    folder_id: uuid.UUID
    filename: str = Field(min_length=1, max_length=255)
    meta: dict[str, str] = Field(default_factory=dict)


class PresignDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_id: uuid.UUID


class PresignDownloadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_id: uuid.UUID


class PresignCopyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_file_id: uuid.UUID
    destination_folder_id: uuid.UUID
    name: str | None = Field(default=None, min_length=1, max_length=255)
    metadata_directive: Literal["COPY", "REPLACE"] = "COPY"
    meta: dict[str, str] = Field(default_factory=dict)


class PresignUploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    headers: dict[str, str]
    expires_at: dt.datetime


@router.post("/presign")
async def presign_upload(
    payload: PresignUploadRequest,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
) -> PresignUploadResponse:
    folder = folder_access_service.require_folder(db, payload.folder_id)
    folder_access_service.require_folder_permission_strict(
        db,
        current_user,
        folder.id,
        Permission.WRITE,
    )
    bucket, key = object_service.build_bucket_and_key_for_destination(
        db, folder=folder, filename=payload.filename
    )
    user_metadata = normalize_user_metadata(payload.meta)
    signed = s3_signing.sign_put_url(
        bucket=bucket,
        key=key,
        headers={
            **{f"x-amz-meta-{name}": value for name, value in user_metadata.items()},
        },
        user_id=current_user.id,
        host=request.headers.get("host", "testserver"),
        ttl_seconds=S.RELIC_SIGNING_TTL_SECONDS,
    )
    event_service.record_event(
        db,
        source="relic_api",
        operation="presign.upload.created",
        actor_user_id=current_user.id,
        request_id=event_service.request_id_from_headers(request.headers),
        folder_ids=[folder.id],
        metadata={"bucket": bucket, "key": key, "filename": payload.filename},
    )
    return PresignUploadResponse(
        url=signed.url,
        headers=signed.headers,
        expires_at=signed.expires_at,
    )


@router.post("/presign-delete")
async def presign_delete(
    payload: PresignDeleteRequest,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
) -> PresignUploadResponse:
    file = object_service.get_file_for_user(
        db, payload.file_id, current_user, Permission.DELETE
    )
    bucket, key = object_service.build_bucket_and_key_for_file(db, file)
    signed = s3_signing.sign_delete_url(
        bucket=bucket,
        key=key,
        user_id=current_user.id,
        host=request.headers.get("host", "testserver"),
        ttl_seconds=S.RELIC_SIGNING_TTL_SECONDS,
    )
    event_service.record_event(
        db,
        source="relic_api",
        operation="presign.delete.created",
        actor_user_id=current_user.id,
        request_id=event_service.request_id_from_headers(request.headers),
        file_ids=[file.id],
        folder_ids=[file.folder_id],
        blob_ids=[file.blob_id],
        metadata={"bucket": bucket, "key": key},
    )
    return PresignUploadResponse(
        url=signed.url,
        headers=signed.headers,
        expires_at=signed.expires_at,
    )


@router.post("/presign-download")
async def presign_download(
    payload: PresignDownloadRequest,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
) -> PresignUploadResponse:
    file = object_service.get_file_for_user(
        db, payload.file_id, current_user, Permission.READ
    )
    bucket, key = object_service.build_bucket_and_key_for_file(db, file)
    signed = s3_signing.sign_get_url(
        bucket=bucket,
        key=key,
        user_id=current_user.id,
        host=request.headers.get("host", "testserver"),
        ttl_seconds=S.RELIC_SIGNING_TTL_SECONDS,
    )
    event_service.record_event(
        db,
        source="relic_api",
        operation="presign.download.created",
        actor_user_id=current_user.id,
        request_id=event_service.request_id_from_headers(request.headers),
        file_ids=[file.id],
        folder_ids=[file.folder_id],
        blob_ids=[file.blob_id],
        metadata={"bucket": bucket, "key": key},
    )
    return PresignUploadResponse(
        url=signed.url,
        headers=signed.headers,
        expires_at=signed.expires_at,
    )


@router.post("/presign-copy")
async def presign_copy(
    payload: PresignCopyRequest,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
) -> PresignUploadResponse:
    source_file = object_service.get_file_for_user(
        db, payload.source_file_id, current_user, Permission.READ
    )
    dest_folder = folder_access_service.require_folder(
        db, payload.destination_folder_id
    )
    folder_access_service.require_folder_permission_strict(
        db, current_user, dest_folder.id, Permission.WRITE
    )

    dest_filename = payload.name or source_file.name
    source_bucket, source_key = object_service.build_bucket_and_key_for_file(
        db, source_file
    )
    dest_bucket, dest_key = object_service.build_bucket_and_key_for_destination(
        db, folder=dest_folder, filename=dest_filename
    )

    if source_bucket == dest_bucket and source_key == dest_key:
        if payload.metadata_directive == "COPY":
            raise BadRequestError(
                "Source and destination must differ when metadata-directive is COPY"
            )

    user_metadata = normalize_user_metadata(payload.meta)
    signed_headers: dict[str, str] = {
        "x-amz-copy-source": f"/{source_bucket}/{source_key}",
        "x-amz-metadata-directive": payload.metadata_directive,
    }
    if payload.metadata_directive == "REPLACE":
        for name, value in user_metadata.items():
            signed_headers[f"x-amz-meta-{name}"] = value

    signed = s3_signing.sign_put_url(
        bucket=dest_bucket,
        key=dest_key,
        headers=signed_headers,
        user_id=current_user.id,
        host=request.headers.get("host", "testserver"),
        ttl_seconds=S.RELIC_SIGNING_TTL_SECONDS,
    )
    event_service.record_event(
        db,
        source="relic_api",
        operation="presign.copy.created",
        actor_user_id=current_user.id,
        request_id=event_service.request_id_from_headers(request.headers),
        file_ids=[source_file.id],
        folder_ids=[source_file.folder_id, dest_folder.id],
        blob_ids=[source_file.blob_id],
        metadata={
            "source_bucket": source_bucket,
            "source_key": source_key,
            "destination_bucket": dest_bucket,
            "destination_key": dest_key,
            "metadata_directive": payload.metadata_directive,
        },
    )
    return PresignUploadResponse(
        url=signed.url,
        headers=signed.headers,
        expires_at=signed.expires_at,
    )


def normalize_user_metadata(meta: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for raw_name, value in meta.items():
        name = raw_name.removeprefix("x-amz-meta-").strip().lower()
        if not name:
            raise BadRequestError("Metadata names cannot be empty")
        if name == "relic-user":
            raise BadRequestError("Metadata name is reserved")
        if "\n" in value or "\r" in value:
            raise BadRequestError("Metadata values cannot contain newlines")
        normalized[name] = value
    return normalized

import datetime as dt
import uuid
from typing import Literal

import settings as S
from enums import Permission
from fastapi import APIRouter, Request
from domain.exceptions import BadRequestError
from pydantic import BaseModel, ConfigDict, Field
from infra.db.stores import folder_access
from infra.db.stores import file_access
from infra.gateway import object_paths
from application.gateway import object_mutations
from application.gateway import object_signing

from api.dependencies import CurrentUser, UnitOfWorkDep

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
    uow: UnitOfWorkDep,
    current_user: CurrentUser,
) -> PresignUploadResponse:
    folder = folder_access.require_folder(uow.session, payload.folder_id)
    folder_access.require_folder_permission_strict(
        uow.session,
        current_user,
        folder.id,
        Permission.WRITE,
    )
    bucket, key = object_paths.build_bucket_and_key_for_destination(
        uow.session, folder=folder, filename=payload.filename
    )
    user_metadata = normalize_user_metadata(payload.meta)
    signed = object_signing.sign_put_url(
        bucket=bucket,
        key=key,
        headers={
            "x-relic-if-none-match": "*",
            **{f"x-amz-meta-{name}": value for name, value in user_metadata.items()},
        },
        user_id=current_user.id,
        host=request.headers.get("host", "testserver"),
        ttl_seconds=S.RELIC_SIGNING_TTL_SECONDS,
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
    uow: UnitOfWorkDep,
    current_user: CurrentUser,
) -> PresignUploadResponse:
    file = file_access.get_file_for_user(
        uow.session, payload.file_id, current_user, Permission.DELETE
    )
    bucket, key = object_paths.build_bucket_and_key_for_file(uow.session, file)
    signed = object_signing.sign_delete_url(
        bucket=bucket,
        key=key,
        user_id=current_user.id,
        host=request.headers.get("host", "testserver"),
        ttl_seconds=S.RELIC_SIGNING_TTL_SECONDS,
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
    uow: UnitOfWorkDep,
    current_user: CurrentUser,
) -> PresignUploadResponse:
    file = file_access.get_file_for_user(
        uow.session, payload.file_id, current_user, Permission.READ
    )
    bucket, key = object_paths.build_bucket_and_key_for_file(uow.session, file)
    blob = file.blob
    if blob is not None:
        object_mutations.touch_blob_access(uow, blob)
    signed = object_signing.sign_get_url(
        bucket=bucket,
        key=key,
        user_id=current_user.id,
        host=request.headers.get("host", "testserver"),
        ttl_seconds=S.RELIC_SIGNING_TTL_SECONDS,
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
    uow: UnitOfWorkDep,
    current_user: CurrentUser,
) -> PresignUploadResponse:
    source_file = file_access.get_file_for_user(
        uow.session, payload.source_file_id, current_user, Permission.READ
    )
    dest_folder = folder_access.require_folder(
        uow.session, payload.destination_folder_id
    )
    folder_access.require_folder_permission_strict(
        uow.session, current_user, dest_folder.id, Permission.WRITE
    )

    dest_filename = payload.name or source_file.name
    source_bucket, source_key = object_paths.build_bucket_and_key_for_file(
        uow.session, source_file
    )
    dest_bucket, dest_key = object_paths.build_bucket_and_key_for_destination(
        uow.session, folder=dest_folder, filename=dest_filename
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

    signed = object_signing.sign_put_url(
        bucket=dest_bucket,
        key=dest_key,
        headers=signed_headers,
        user_id=current_user.id,
        host=request.headers.get("host", "testserver"),
        ttl_seconds=S.RELIC_SIGNING_TTL_SECONDS,
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

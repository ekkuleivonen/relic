import datetime as dt
import uuid
from typing import Literal

import settings as S
from fastapi import APIRouter, Request
from domain.exceptions import BadRequestError
from domain.files.meta import is_reserved_user_metadata_key
from pydantic import BaseModel, ConfigDict, Field
from application.context import Actor
from application.control_plane import presigned_access
from application.gateway import object_mutations
from application.gateway import object_signing

from api.dependencies import CurrentUser, UnitOfWorkDep

router = APIRouter()


class PresignUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    folder_id: uuid.UUID = Field(description="Destination folder for the new file.")
    filename: str = Field(
        min_length=1,
        max_length=255,
        description="File name (must not contain `/`).",
    )
    meta: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "User metadata stored on the file. Keys become `x-amz-meta-{key}` on the "
            "signed PUT. `pithosys-user` is reserved."
        ),
    )


class PresignDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_id: uuid.UUID = Field(description="File to delete via signed DELETE.")


class PresignDownloadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_id: uuid.UUID = Field(description="File to download via signed GET.")


class PresignCopyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_file_id: uuid.UUID = Field(description="File to copy from.")
    destination_folder_id: uuid.UUID = Field(description="Folder for the copy.")
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Destination filename. Defaults to source name.",
    )
    metadata_directive: Literal["COPY", "REPLACE"] = Field(
        default="COPY",
        description="S3 metadata directive for the copy PUT.",
    )
    meta: dict[str, str] = Field(
        default_factory=dict,
        description="New metadata when `metadata_directive` is REPLACE.",
    )


class PresignUploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(
        description=(
            "Path-style S3 URL relative to the Pithosys host, percent-encoded where "
            "needed (e.g. `/s3/Local%20Testing/file.csv?X-Amz-...`). Prepend your "
            "API base URL's origin for an absolute URL. Same location as "
            "`FileRead.gateway`; for native SigV4 use literal `bucket`/`key` instead."
        ),
    )
    headers: dict[str, str] = Field(
        description="Headers to send with the signed request (includes SigV4 params)."
    )
    expires_at: dt.datetime = Field(description="UTC expiry of the signature.")


@router.post(
    "/presign",
    summary="Presign upload",
    description=(
        "Return a signed PUT URL under `/s3/{bucket}/{key}`. "
        "Replay with the returned `url`, `headers`, and request body to create the file."
    ),
)
async def presign_upload(
    payload: PresignUploadRequest,
    request: Request,
    uow: UnitOfWorkDep,
    current_user: CurrentUser,
) -> PresignUploadResponse:
    actor = Actor.from_user(current_user)
    folder = presigned_access.require_folder_for_write(
        uow, actor=actor, folder_id=payload.folder_id
    )
    presigned_access.require_folder_accepts_files(folder)
    bucket, key = presigned_access.bucket_and_key_for_destination(
        uow, folder=folder, filename=payload.filename
    )
    user_metadata = normalize_user_metadata(payload.meta)
    signed = object_signing.sign_put_url(
        bucket=bucket,
        key=key,
        headers={
            "x-pithosys-if-none-match": "*",
            **{f"x-amz-meta-{name}": value for name, value in user_metadata.items()},
        },
        user_id=current_user.id,
        host=request.headers.get("host", "testserver"),
        ttl_seconds=S.PITHOSYS_SIGNING_TTL_SECONDS,
    )
    return PresignUploadResponse(
        url=signed.url,
        headers=signed.headers,
        expires_at=signed.expires_at,
    )


@router.post(
    "/presign-delete",
    summary="Presign delete",
    description="Return a signed DELETE URL for an existing file.",
)
async def presign_delete(
    payload: PresignDeleteRequest,
    request: Request,
    uow: UnitOfWorkDep,
    current_user: CurrentUser,
) -> PresignUploadResponse:
    actor = Actor.from_user(current_user)
    file = presigned_access.get_file_for_delete(uow, actor=actor, file_id=payload.file_id)
    bucket, key = presigned_access.bucket_and_key_for_file(uow, file)
    signed = object_signing.sign_delete_url(
        bucket=bucket,
        key=key,
        user_id=current_user.id,
        host=request.headers.get("host", "testserver"),
        ttl_seconds=S.PITHOSYS_SIGNING_TTL_SECONDS,
    )
    return PresignUploadResponse(
        url=signed.url,
        headers=signed.headers,
        expires_at=signed.expires_at,
    )


@router.post(
    "/presign-download",
    summary="Presign download",
    description=(
        "Return a signed GET URL to stream object bytes. The unsigned location is "
        "also on `FileRead.gateway` (`bucket`, `key`, `object_uri`)."
    ),
)
async def presign_download(
    payload: PresignDownloadRequest,
    request: Request,
    uow: UnitOfWorkDep,
    current_user: CurrentUser,
) -> PresignUploadResponse:
    actor = Actor.from_user(current_user)
    file = presigned_access.get_file_for_read(uow, actor=actor, file_id=payload.file_id)
    bucket, key = presigned_access.bucket_and_key_for_file(uow, file)
    blob = file.blob
    if blob is not None:
        object_mutations.touch_blob_access(uow, blob)
    signed = object_signing.sign_get_url(
        bucket=bucket,
        key=key,
        user_id=current_user.id,
        host=request.headers.get("host", "testserver"),
        ttl_seconds=S.PITHOSYS_SIGNING_TTL_SECONDS,
    )
    return PresignUploadResponse(
        url=signed.url,
        headers=signed.headers,
        expires_at=signed.expires_at,
    )


@router.post(
    "/presign-copy",
    summary="Presign copy",
    description=(
        "Return a signed PUT URL that performs an S3 copy from a source file. "
        "Send the returned request with `x-amz-copy-source` in headers."
    ),
)
async def presign_copy(
    payload: PresignCopyRequest,
    request: Request,
    uow: UnitOfWorkDep,
    current_user: CurrentUser,
) -> PresignUploadResponse:
    actor = Actor.from_user(current_user)
    source_file = presigned_access.get_file_for_read(
        uow, actor=actor, file_id=payload.source_file_id
    )
    dest_folder = presigned_access.require_folder_for_write(
        uow, actor=actor, folder_id=payload.destination_folder_id
    )
    presigned_access.require_folder_accepts_files(dest_folder)

    dest_filename = payload.name or source_file.name
    source_bucket, source_key = presigned_access.bucket_and_key_for_file(
        uow, source_file
    )
    dest_bucket, dest_key = presigned_access.bucket_and_key_for_destination(
        uow, folder=dest_folder, filename=dest_filename
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
        ttl_seconds=S.PITHOSYS_SIGNING_TTL_SECONDS,
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
        if is_reserved_user_metadata_key(name):
            raise BadRequestError("Metadata name is reserved")
        if "\n" in value or "\r" in value:
            raise BadRequestError("Metadata values cannot contain newlines")
        normalized[name] = value
    return normalized

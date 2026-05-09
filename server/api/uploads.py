import datetime as dt
import uuid

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

import settings as S
from api.dependencies import CurrentUser
from database import DbSession
from managers.exceptions import BadRequestError
from schema_plan import Permission
from services import folder_access as folder_access_service
from services import objects as object_service
from services import s3_signing

router = APIRouter()


class PresignUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    folder_id: uuid.UUID
    filename: str = Field(min_length=1, max_length=255)
    file_size: int = Field(ge=0)
    mime_type: str | None = Field(default=None, max_length=255)
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
    bucket, key = resolve_gateway_path(db, folder, payload.filename)
    user_metadata = normalize_user_metadata(payload.meta)
    predicted_meta = object_service.build_predicted_file_meta(
        key=key,
        file_size=payload.file_size,
        content_type=payload.mime_type,
        user_metadata=user_metadata,
    )
    object_service.validate_metadata_against_schema(folder, predicted_meta)
    signed = s3_signing.sign_put_url(
        bucket=bucket,
        key=key,
        headers={
            "content-type": predicted_meta["mime_type"],
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


def resolve_gateway_path(db, folder, filename: str) -> tuple[str, str]:
    if "/" in filename:
        raise BadRequestError("Filename cannot contain '/'")
    folder_path = folder_access_service.resolve_folder_path(db, folder)
    parts = [part for part in folder_path.split("/") if part]
    if not parts:
        raise BadRequestError("Cannot upload files to the root folder")
    bucket = parts[0]
    key_parts = [*parts[1:], filename]
    return bucket, "/".join(key_parts)


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

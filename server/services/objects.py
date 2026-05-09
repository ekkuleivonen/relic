import datetime as dt
import hashlib
import posixpath
from dataclasses import dataclass
from pathlib import PurePosixPath

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from jsonschema import ValidationError, validate
from sqlalchemy import select
from sqlalchemy.orm import Session

from managers.exceptions import BadRequestError, ConflictError, ResourceNotFound
from models import Blob, Bucket, File, Folder, User
from schema_plan import BucketTier, Permission
from services import folder_access as folder_access_service
from services.placement import choose_bucket


@dataclass(frozen=True)
class PutObjectResult:
    file: File
    blob: Blob
    etag: str


def put_object(
    db: Session,
    *,
    bucket_name: str,
    key: str,
    body: bytes,
    content_type: str | None,
    user_metadata: dict[str, str],
    current_user: User | None = None,
) -> PutObjectResult:
    folder, file_name = resolve_object_path(
        db,
        bucket_name=bucket_name,
        key=key,
        current_user=current_user,
    )
    if current_user is not None:
        folder_access_service.require_folder_permission(
            db,
            current_user,
            folder.id,
            Permission.WRITE,
        )
    ensure_file_name_available(db, folder.id, file_name)
    meta = build_file_meta(
        key=key,
        body=body,
        content_type=content_type,
        user_metadata=user_metadata,
    )
    validate_metadata_against_schema(folder, meta)

    digest = hashlib.sha256(body).digest()
    digest_hex = digest.hex()
    blob = db.scalar(select(Blob).where(Blob.content_hash == digest))

    if blob:
        blob.refcount += 1
    else:
        bucket = choose_bucket(
            db,
            tier=BucketTier(folder.min_tier),
            size_bytes=len(body),
        )
        blob = create_blob(
            db,
            bucket=bucket,
            digest=digest,
            body=body,
        )

    file = File(
        folder_id=folder.id,
        blob_id=blob.id,
        name=file_name,
        meta=meta,
    )
    db.add(file)
    db.commit()
    db.refresh(file)
    db.refresh(blob)
    return PutObjectResult(file=file, blob=blob, etag=digest_hex)


def resolve_object_path(
    db: Session,
    *,
    bucket_name: str,
    key: str,
    current_user: User | None = None,
) -> tuple[Folder, str]:
    normalized_key = normalize_key(key)
    parts = [part for part in PurePosixPath(normalized_key).parts if part not in ("", ".")]
    if not parts:
        raise BadRequestError("Object key must include a file name")

    root = db.scalar(select(Folder).where(Folder.parent_id.is_(None)))
    if not root:
        raise ResourceNotFound("Root folder not found")

    bucket_folder = db.scalar(
        select(Folder).where(Folder.parent_id == root.id, Folder.name == bucket_name)
    )
    if not bucket_folder:
        raise ResourceNotFound("Bucket folder not found")

    parent = bucket_folder
    for folder_name in parts[:-1]:
        parent = get_or_create_child_folder(
            db,
            parent=parent,
            name=folder_name,
            current_user=current_user,
        )
    return parent, parts[-1]


def normalize_key(key: str) -> str:
    normalized_key = posixpath.normpath(key)
    if normalized_key.startswith("../") or normalized_key == "..":
        raise BadRequestError("Object key cannot escape the bucket")
    return normalized_key


def get_or_create_child_folder(
    db: Session,
    *,
    parent: Folder,
    name: str,
    current_user: User | None = None,
) -> Folder:
    child = db.scalar(
        select(Folder).where(Folder.parent_id == parent.id, Folder.name == name)
    )
    if child:
        return child

    if current_user is not None:
        folder_access_service.require_folder_permission(
            db,
            current_user,
            parent.id,
            Permission.WRITE,
        )

    child = Folder(
        parent_id=parent.id,
        name=name,
        schema=parent.schema,
        cooldown_days=parent.cooldown_days,
        min_tier=parent.min_tier,
    )
    db.add(child)
    db.flush()
    return child


def ensure_file_name_available(db: Session, folder_id, file_name: str) -> None:
    existing = db.scalar(
        select(File).where(File.folder_id == folder_id, File.name == file_name)
    )
    if existing:
        raise ConflictError("File already exists")


def create_blob(
    db: Session,
    *,
    bucket: Bucket,
    digest: bytes,
    body: bytes,
) -> Blob:
    blob = Blob(
        bucket_id=bucket.id,
        bucket_key="",
        content_hash=digest,
        refcount=1,
    )
    db.add(blob)
    db.flush()

    blob.bucket_key = build_blob_bucket_key(blob)
    upload_blob(bucket=bucket, bucket_key=blob.bucket_key, body=body)

    bucket.object_count += 1
    bucket.current_size_bytes += len(body)
    return blob


def build_blob_bucket_key(blob: Blob) -> str:
    created_at = blob.created_at or dt.datetime.now(dt.UTC)
    return f"{created_at:%Y/%m/%d}/{blob.id}"


def upload_blob(*, bucket: Bucket, bucket_key: str, body: bytes) -> None:
    try:
        client = boto3.client(
            service_name="s3",
            endpoint_url=bucket.endpoint,
            region_name=bucket.region,
            aws_access_key_id=bucket.key_id,
            aws_secret_access_key=bucket.secret_access_key,
        )
        client.put_object(Bucket=bucket.bucket, Key=bucket_key, Body=body)
    except (BotoCoreError, ClientError) as exc:
        raise BadRequestError("Failed to upload object to bucket") from exc


def build_file_meta(
    *,
    key: str,
    body: bytes,
    content_type: str | None,
    user_metadata: dict[str, str],
) -> dict:
    file_name = PurePosixPath(key).name
    extension = PurePosixPath(file_name).suffix
    return {
        **user_metadata,
        "original_name": file_name,
        "file_size": len(body),
        "mime_type": content_type or "application/octet-stream",
        "extension": extension,
    }


def build_predicted_file_meta(
    *,
    key: str,
    file_size: int,
    content_type: str | None,
    user_metadata: dict[str, str],
) -> dict:
    file_name = PurePosixPath(key).name
    extension = PurePosixPath(file_name).suffix
    return {
        **user_metadata,
        "original_name": file_name,
        "file_size": file_size,
        "mime_type": content_type or "application/octet-stream",
        "extension": extension,
    }


def validate_metadata_against_schema(folder: Folder, meta: dict) -> None:
    try:
        validate(instance=meta, schema=folder.schema)
    except ValidationError as exc:
        raise BadRequestError(f"Invalid metadata: {exc.message}") from exc

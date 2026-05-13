import base64
import binascii
import datetime as dt
from dataclasses import dataclass

from constants import S3_LISTING_DEFAULT_MAX_KEYS, S3_LISTING_MAX_KEYS_LIMIT
from enums import Permission
from domain.exceptions import BadRequestError, ResourceNotFound
from models import File, Folder, User
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from services import folder_access as folder_access_service


@dataclass(frozen=True)
class BucketListingItem:
    name: str
    created_at: dt.datetime


@dataclass(frozen=True)
class ObjectListingItem:
    key: str
    file: File


@dataclass(frozen=True)
class ListObjectsV2Page:
    bucket: str
    prefix: str
    delimiter: str | None
    max_keys: int
    continuation_token: str | None
    start_after: str | None
    contents: list[ObjectListingItem]
    common_prefixes: list[str]
    is_truncated: bool
    next_continuation_token: str | None
    key_count: int


def list_visible_buckets(db: Session, user: User) -> list[BucketListingItem]:
    root = require_root_folder(db)
    permissions = folder_access_service.effective_permissions_by_folder(db, user)
    folders = db.scalars(
        select(Folder).where(Folder.parent_id == root.id).order_by(Folder.name)
    ).all()
    return [
        BucketListingItem(name=folder.name, created_at=folder.created_at)
        for folder in folders
        if permissions.get(folder.id, 0) & int(Permission.READ)
    ]


def require_visible_bucket(db: Session, user: User, bucket_name: str) -> Folder:
    root = require_root_folder(db)
    bucket = db.scalar(
        select(Folder).where(Folder.parent_id == root.id, Folder.name == bucket_name)
    )
    if bucket is None:
        raise ResourceNotFound("Bucket not found")

    folder_access_service.require_folder_permission(
        db, user, bucket.id, Permission.READ
    )
    return bucket


def list_objects_v2(
    db: Session,
    user: User,
    *,
    bucket_name: str,
    prefix: str = "",
    delimiter: str | None = None,
    max_keys: int = S3_LISTING_DEFAULT_MAX_KEYS,
    continuation_token: str | None = None,
    start_after: str | None = None,
) -> ListObjectsV2Page:
    bucket = require_visible_bucket(db, user, bucket_name)
    normalized_prefix = normalize_prefix(prefix)
    normalized_delimiter = normalize_delimiter(delimiter)
    page_size = normalize_max_keys(max_keys)
    offset = decode_continuation_token(continuation_token)

    candidates = build_listing_candidates(
        db,
        user,
        bucket=bucket,
        prefix=normalized_prefix,
        delimiter=normalized_delimiter,
        start_after=start_after or None,
    )
    page_candidates = candidates[offset : offset + page_size]
    next_offset = offset + len(page_candidates)
    is_truncated = next_offset < len(candidates)
    next_token = encode_continuation_token(next_offset) if is_truncated else None

    contents = [
        item
        for kind, item in page_candidates
        if kind == "content" and isinstance(item, ObjectListingItem)
    ]
    common_prefixes = [
        item
        for kind, item in page_candidates
        if kind == "prefix" and isinstance(item, str)
    ]
    return ListObjectsV2Page(
        bucket=bucket_name,
        prefix=normalized_prefix,
        delimiter=normalized_delimiter,
        max_keys=page_size,
        continuation_token=continuation_token,
        start_after=start_after,
        contents=contents,
        common_prefixes=common_prefixes,
        is_truncated=is_truncated,
        next_continuation_token=next_token,
        key_count=len(page_candidates),
    )


def build_listing_candidates(
    db: Session,
    user: User,
    *,
    bucket: Folder,
    prefix: str,
    delimiter: str | None,
    start_after: str | None,
) -> list[tuple[str, ObjectListingItem | str]]:
    permissions = folder_access_service.effective_permissions_by_folder(db, user)
    bucket_path = folder_access_service.resolve_folder_path(db, bucket)
    folders = list(
        db.scalars(
            select(Folder).where(Folder.id != bucket.id).order_by(Folder.name)
        ).all()
    )
    files = list(
        db.scalars(
            select(File).options(selectinload(File.blob)).order_by(File.name)
        ).all()
    )
    folder_ids = {
        bucket.id,
        *(folder.id for folder in folders),
        *(file.folder_id for file in files),
    }
    paths = folder_access_service.compute_folder_paths(db, folder_ids)

    seen_prefixes: set[str] = set()
    candidates: dict[str, tuple[str, ObjectListingItem | str]] = {}

    if delimiter:
        for folder in folders:
            if not permissions.get(folder.id, 0) & int(Permission.READ):
                continue
            folder_path = paths[folder.id]
            if not folder_path.startswith(f"{bucket_path.rstrip('/')}/"):
                continue
            key_prefix = path_to_key(bucket_path, folder_path, is_folder=True)
            collapsed = collapse_common_prefix(key_prefix, prefix, delimiter)
            if (
                start_after is not None
                and collapsed is not None
                and collapsed <= start_after
            ):
                continue
            if collapsed is not None and collapsed not in seen_prefixes:
                seen_prefixes.add(collapsed)
                candidates[collapsed] = ("prefix", collapsed)

    for file in files:
        if not permissions.get(file.folder_id, 0) & int(Permission.READ):
            continue
        folder_path = paths[file.folder_id]
        if folder_path != bucket_path and not folder_path.startswith(
            f"{bucket_path.rstrip('/')}/"
        ):
            continue
        key = f"{path_to_key(bucket_path, folder_path)}{file.name}"
        if not key.startswith(prefix):
            continue
        if start_after is not None and key <= start_after:
            continue

        if delimiter:
            collapsed = collapse_common_prefix(key, prefix, delimiter)
            if (
                start_after is not None
                and collapsed is not None
                and collapsed <= start_after
            ):
                continue
            if collapsed is not None:
                if collapsed not in seen_prefixes:
                    seen_prefixes.add(collapsed)
                    candidates[collapsed] = ("prefix", collapsed)
                continue
        candidates[key] = ("content", ObjectListingItem(key=key, file=file))

    return [candidates[key] for key in sorted(candidates)]


def path_to_key(bucket_path: str, folder_path: str, *, is_folder: bool = False) -> str:
    bucket_prefix = bucket_path.rstrip("/")
    if folder_path == bucket_path:
        relative = ""
    else:
        relative = folder_path.removeprefix(f"{bucket_prefix}/").strip("/")
    if not relative:
        return ""
    return f"{relative}/"


def collapse_common_prefix(key: str, prefix: str, delimiter: str) -> str | None:
    if not key.startswith(prefix):
        return None
    remainder = key[len(prefix) :]
    delimiter_index = remainder.find(delimiter)
    if delimiter_index == -1:
        return None
    return f"{prefix}{remainder[: delimiter_index + len(delimiter)]}"


def normalize_prefix(prefix: str | None) -> str:
    value = prefix or ""
    if value.startswith("/"):
        raise BadRequestError("Prefix cannot start with '/'")
    if "../" in value or value == ".." or value.startswith("../"):
        raise BadRequestError("Prefix cannot escape the bucket")
    return value


def normalize_delimiter(delimiter: str | None) -> str | None:
    if delimiter in (None, ""):
        return None
    if delimiter != "/":
        raise BadRequestError("Only '/' delimiter is supported")
    return delimiter


def normalize_max_keys(max_keys: int) -> int:
    if max_keys < 0:
        raise BadRequestError("max-keys must be greater than or equal to 0")
    return min(max_keys, S3_LISTING_MAX_KEYS_LIMIT)


def encode_continuation_token(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode()


def decode_continuation_token(token: str | None) -> int:
    if not token:
        return 0
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        offset = int(decoded)
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise BadRequestError("Invalid continuation-token") from exc
    if offset < 0:
        raise BadRequestError("Invalid continuation-token")
    return offset


def require_root_folder(db: Session) -> Folder:
    root = db.scalar(select(Folder).where(Folder.parent_id.is_(None)))
    if root is None:
        raise ResourceNotFound("Root folder not found")
    return root

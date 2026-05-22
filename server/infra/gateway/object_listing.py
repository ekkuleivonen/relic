import base64
import binascii
import datetime as dt
from dataclasses import dataclass

from constants import S3_LISTING_DEFAULT_MAX_KEYS, S3_LISTING_MAX_KEYS_LIMIT
from enums import Permission
from domain.exceptions import BadRequestError
from infra.db.models import File, Folder, User
from infra.gateway.bucket import gateway_bucket_name, require_gateway_bucket
from infra.gateway.object_paths import require_root_folder
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from infra.db.stores import folder_access
from infra.db.stores.filesystem import collect_descendant_folder_ids


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


def folder_path_to_key_prefix(folder_path: str) -> str:
    return "/".join(part for part in folder_path.split("/") if part)


def object_key_for_file(*, folder_path: str, filename: str) -> str:
    prefix = folder_path_to_key_prefix(folder_path)
    return f"{prefix}/{filename}" if prefix else filename


def list_visible_buckets(db: Session, user: User) -> list[BucketListingItem]:
    del user
    root = require_root_folder(db)
    return [
        BucketListingItem(name=gateway_bucket_name(), created_at=root.created_at),
    ]


def require_visible_bucket(db: Session, user: User, bucket_name: str) -> Folder:
    del user
    require_gateway_bucket(bucket_name)
    return require_root_folder(db)


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
    require_gateway_bucket(bucket_name)
    normalized_prefix = normalize_prefix(prefix)
    normalized_delimiter = normalize_delimiter(delimiter)
    page_size = normalize_max_keys(max_keys)
    offset = decode_continuation_token(continuation_token)
    anchor = resolve_listing_folder_from_prefix(db, normalized_prefix)

    candidates = build_listing_candidates(
        db,
        user,
        anchor_folder=anchor,
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
    anchor_folder: Folder,
    prefix: str,
    delimiter: str | None,
    start_after: str | None,
) -> list[tuple[str, ObjectListingItem | str]]:
    permissions = folder_access.effective_permissions_by_folder(db, user)
    folders, files = _load_listing_rows(
        db, anchor_folder=anchor_folder, prefix=prefix, delimiter=delimiter
    )
    folder_ids = {
        anchor_folder.id,
        *(folder.id for folder in folders),
        *(file.folder_id for file in files),
    }
    paths = folder_access.compute_folder_paths(db, folder_ids)

    seen_prefixes: set[str] = set()
    candidates: dict[str, tuple[str, ObjectListingItem | str]] = {}

    if delimiter:
        for folder in folders:
            if not permissions.get(folder.id, 0) & int(Permission.READ):
                continue
            key_prefix = f"{folder_path_to_key_prefix(paths[folder.id])}/"
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
        key = object_key_for_file(folder_path=paths[file.folder_id], filename=file.name)
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


def _load_listing_rows(
    db: Session,
    *,
    anchor_folder: Folder,
    prefix: str,
    delimiter: str | None,
) -> tuple[list[Folder], list[File]]:
    if delimiter and (not prefix or prefix.endswith("/")):
        folders = list(
            db.scalars(
                select(Folder)
                .where(Folder.parent_id == anchor_folder.id)
                .order_by(Folder.name)
            ).all()
        )
        files = list(
            db.scalars(
                select(File)
                .where(File.folder_id == anchor_folder.id)
                .options(selectinload(File.blob))
                .order_by(File.name)
            ).all()
        )
        return folders, files

    subtree_ids = collect_descendant_folder_ids(db, anchor_folder.id)
    subtree_id_set = set(subtree_ids)
    folders = list(
        db.scalars(
            select(Folder)
            .where(Folder.id.in_(subtree_id_set), Folder.id != anchor_folder.id)
            .order_by(Folder.name)
        ).all()
    )
    files = list(
        db.scalars(
            select(File)
            .where(File.folder_id.in_(subtree_id_set))
            .options(selectinload(File.blob))
            .order_by(File.name)
        ).all()
    )
    return folders, files


def resolve_listing_folder_from_prefix(db: Session, prefix: str) -> Folder:
    root = require_root_folder(db)
    if not prefix:
        return root
    parts = [part for part in prefix.split("/") if part]
    current = root
    for part in parts:
        child = db.scalar(
            select(Folder).where(
                Folder.parent_id == current.id,
                Folder.name == part,
            )
        )
        if child is None:
            return current
        current = child
    return current


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

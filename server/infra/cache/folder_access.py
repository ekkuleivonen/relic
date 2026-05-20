"""Process/request TTL caches for folder tree hot paths."""

import uuid

import settings as S
from domain.filesystem.paths import build_folder_paths
from infra.cache.codec import (
    decode_folder_tree_rows,
    decode_uuid_int_map,
    decode_uuid_str_map,
    effective_permissions_cache_key,
    encode_folder_tree_rows,
    encode_uuid_int_map,
    encode_uuid_str_map,
    folder_paths_cache_key,
    folder_tree_cache_key,
)
from infra.cache.hotpath import request_cache
from infra.cache.scope import deployment_scope
from infra.cache.tiered import get_tiered_cache
from infra.db.models import Folder
from infra.db.stores.folder_access_types import FolderTreeRow
from sqlalchemy import select
from sqlalchemy.orm import Session


def clear_hotpath_cache(db: Session | None = None) -> None:
    get_tiered_cache("folder_tree").invalidate()
    get_tiered_cache("folder_paths").invalidate()
    get_tiered_cache("effective_permissions").invalidate()
    if db is not None:
        db.info.pop("folder_hotpath_cache", None)


def get_cached_effective_permissions(
    process_key: tuple[str, uuid.UUID, int],
) -> dict[uuid.UUID, int] | None:
    scope, user_id, required = process_key
    cached = get_tiered_cache("effective_permissions").get(
        effective_permissions_cache_key(scope, user_id, required)
    )
    if cached is None:
        return None
    return decode_uuid_int_map(cached)


def set_cached_effective_permissions(
    process_key: tuple[str, uuid.UUID, int],
    permissions: dict[uuid.UUID, int],
) -> None:
    scope, user_id, required = process_key
    get_tiered_cache("effective_permissions").set(
        effective_permissions_cache_key(scope, user_id, required),
        encode_uuid_int_map(permissions),
        ttl_seconds=S.FOLDER_METADATA_CACHE_TTL_SECONDS,
    )


def cached_folder_tree_rows(db: Session) -> tuple[FolderTreeRow, ...]:
    request_key = "folder_tree_rows"
    cache = request_cache(db)
    if request_key in cache:
        return cache[request_key]

    scope = deployment_scope()
    cache_key = folder_tree_cache_key(scope)
    tiered = get_tiered_cache("folder_tree")
    cached = tiered.get(cache_key)
    if cached is not None:
        rows = decode_folder_tree_rows(cached)
        cache[request_key] = rows
        return rows

    rows = tuple(
        FolderTreeRow(id=folder_id, parent_id=parent_id, name=name)
        for folder_id, parent_id, name in db.execute(
            select(Folder.id, Folder.parent_id, Folder.name)
        ).all()
    )
    tiered.set(
        cache_key,
        encode_folder_tree_rows(rows),
        ttl_seconds=S.FOLDER_METADATA_CACHE_TTL_SECONDS,
    )
    cache[request_key] = rows
    return rows


def derive_folder_paths(db: Session) -> dict[uuid.UUID, str]:
    rows = cached_folder_tree_rows(db)
    parent_of = {row.id: row.parent_id for row in rows}
    name_of = {row.id: row.name for row in rows}
    return build_folder_paths(parent_of, name_of)


def cached_folder_paths(db: Session) -> dict[uuid.UUID, str]:
    request_key = "folder_paths"
    cache = request_cache(db)
    if request_key in cache:
        return cache[request_key]

    scope = deployment_scope()
    cache_key = folder_paths_cache_key(scope)
    tiered = get_tiered_cache("folder_paths")
    cached = tiered.get(cache_key)
    if cached is not None:
        paths = decode_uuid_str_map(cached)
        cache[request_key] = paths
        return paths

    paths = derive_folder_paths(db)
    tiered.set(
        cache_key,
        encode_uuid_str_map(paths),
        ttl_seconds=S.FOLDER_METADATA_CACHE_TTL_SECONDS,
    )
    cache[request_key] = paths
    return paths

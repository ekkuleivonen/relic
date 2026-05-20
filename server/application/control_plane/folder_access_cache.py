"""Process/request TTL caches for folder tree hot paths."""

import uuid

import settings as S
from infra.db.models import Folder
from sqlalchemy import select
from sqlalchemy.orm import Session

from application.control_plane.folder_access_types import FolderTreeRow
from domain.filesystem.paths import build_folder_paths
from infra.cache.hotpath import (
    TtlCacheEntry,
    engine_cache_key,
    get_ttl,
    request_cache,
    set_ttl,
)

_FOLDER_TREE_CACHE: dict[int, TtlCacheEntry] = {}
_FOLDER_PATHS_CACHE: dict[int, TtlCacheEntry] = {}
_EFFECTIVE_PERMISSIONS_CACHE: dict[tuple[int, uuid.UUID, int], TtlCacheEntry] = {}


def clear_hotpath_cache(db: Session | None = None) -> None:
    if db is None:
        _FOLDER_TREE_CACHE.clear()
        _FOLDER_PATHS_CACHE.clear()
        _EFFECTIVE_PERMISSIONS_CACHE.clear()
        return

    key = engine_cache_key(db)
    _FOLDER_TREE_CACHE.pop(key, None)
    _FOLDER_PATHS_CACHE.pop(key, None)
    for cache_key in list(_EFFECTIVE_PERMISSIONS_CACHE):
        if cache_key[0] == key:
            _EFFECTIVE_PERMISSIONS_CACHE.pop(cache_key, None)
    db.info.pop("folder_hotpath_cache", None)


def get_cached_effective_permissions(
    process_key: tuple[int, uuid.UUID, int],
) -> dict[uuid.UUID, int] | None:
    return get_ttl(_EFFECTIVE_PERMISSIONS_CACHE, process_key)


def set_cached_effective_permissions(
    process_key: tuple[int, uuid.UUID, int],
    permissions: dict[uuid.UUID, int],
) -> None:
    set_ttl(
        _EFFECTIVE_PERMISSIONS_CACHE,
        process_key,
        permissions,
        ttl_seconds=S.FOLDER_METADATA_CACHE_TTL_SECONDS,
    )


def cached_folder_tree_rows(db: Session) -> tuple[FolderTreeRow, ...]:
    request_key = "folder_tree_rows"
    cache = request_cache(db)
    if request_key in cache:
        return cache[request_key]

    key = engine_cache_key(db)
    cached = get_ttl(_FOLDER_TREE_CACHE, key)
    if cached is not None:
        cache[request_key] = cached
        return cached

    rows = tuple(
        FolderTreeRow(id=folder_id, parent_id=parent_id, name=name)
        for folder_id, parent_id, name in db.execute(
            select(Folder.id, Folder.parent_id, Folder.name)
        ).all()
    )
    set_ttl(
        _FOLDER_TREE_CACHE,
        key,
        rows,
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

    key = engine_cache_key(db)
    cached = get_ttl(_FOLDER_PATHS_CACHE, key)
    if cached is not None:
        cache[request_key] = cached
        return cached

    paths = derive_folder_paths(db)
    set_ttl(
        _FOLDER_PATHS_CACHE,
        key,
        paths,
        ttl_seconds=S.FOLDER_METADATA_CACHE_TTL_SECONDS,
    )
    cache[request_key] = paths
    return paths

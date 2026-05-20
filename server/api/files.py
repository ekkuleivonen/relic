import datetime as dt
import uuid

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies import CurrentUser
from constants import (
    FILESYSTEM_DEFAULT_LIST_LIMIT,
    FILESYSTEM_MAX_LIST_LIMIT,
    SEARCH_DEFAULT_FACET_TOP,
    SEARCH_DEFAULT_LIMIT,
    SEARCH_MAX_FACET_TOP,
    SEARCH_MAX_LIMIT,
)
from database import DbSession
from models import File
from services import files as files_service
from services import filesystem as filesystem_service
from services import search as search_service

router = APIRouter()

"""
File CRUD - the logical references inside folders.

Note: byte upload/download lives at the S3 gateway, not here. These routes
manage metadata records, queries, and atomic operations like move/rename.
"""


class FileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    folder_id: uuid.UUID
    blob_id: uuid.UUID
    actor_id: uuid.UUID
    actor_name: str | None
    name: str
    meta: dict
    size_bytes: int
    mimetype: str
    extension: str
    created_at: dt.datetime
    updated_at: dt.datetime

    @classmethod
    def from_file(cls, file: File) -> "FileRead":
        blob = file.blob
        return cls(
            id=file.id,
            folder_id=file.folder_id,
            blob_id=file.blob_id,
            actor_id=file.actor_id,
            actor_name=file.actor_name,
            name=file.name,
            meta=file.meta or {},
            size_bytes=blob.size_bytes if blob is not None else 0,
            mimetype=blob.mimetype if blob is not None else "application/octet-stream",
            extension=blob.extension if blob is not None else "",
            created_at=file.created_at,
            updated_at=file.updated_at,
        )


class MoveFileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    destination_folder_id: uuid.UUID
    name: str | None = Field(default=None, min_length=1, max_length=255)


class RenameFileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)


class PatchFileMetaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meta: dict = Field(default_factory=dict)


class FacetValueRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    count: int


class FacetsRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tags: list[FacetValueRead]
    mimetypes: list[FacetValueRead]
    extensions: list[FacetValueRead]
    kvs_keys: list[FacetValueRead]
    total: int


class FileSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[FileRead]
    total: int
    limit: int
    offset: int


class FileListResponse(BaseModel):
    """Paginated folder listing for ``GET /files/``."""

    model_config = ConfigDict(extra="forbid")

    items: list[FileRead]
    total: int
    limit: int
    offset: int


@router.get("/")
async def list_files(
    db: DbSession,
    current_user: CurrentUser,
    folder_id: uuid.UUID | None = None,
    recursive: bool = False,
    limit: int = Query(
        default=FILESYSTEM_DEFAULT_LIST_LIMIT,
        ge=1,
        le=FILESYSTEM_MAX_LIST_LIMIT,
    ),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="name"),
    order: str = Query(default="asc"),
) -> FileListResponse:
    page = filesystem_service.list_files(
        db,
        current_user,
        folder_id=folder_id,
        recursive=recursive,
        limit=limit,
        offset=offset,
        sort=sort,
        order=order,
    )
    return FileListResponse(
        items=[FileRead.from_file(file) for file in page.items],
        total=page.total,
        limit=limit,
        offset=offset,
    )


@router.get("/search")
async def search_files(
    db: DbSession,
    current_user: CurrentUser,
    q: str | None = None,
    tag: list[str] = Query(default_factory=list),
    require_all_tags: bool = False,
    keyword: list[str] = Query(default_factory=list),
    mimetype: list[str] = Query(default_factory=list),
    extension: list[str] = Query(default_factory=list),
    min_size: int | None = None,
    max_size: int | None = None,
    actor_id: uuid.UUID | None = None,
    folder_id: uuid.UUID | None = None,
    recursive: bool = False,
    created_after: dt.datetime | None = None,
    created_before: dt.datetime | None = None,
    kv: list[str] = Query(default_factory=list),
    sort: str = "updated_at",
    order: str = "desc",
    limit: int = Query(default=SEARCH_DEFAULT_LIMIT, ge=1, le=SEARCH_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> FileSearchResponse:
    """Faceted, filterable search over file metadata.

    All array params (`tag`, `keyword`, `mimetype`, `extension`, `kv`) accept
    multiple values via repeated query params. `kv` items use the syntax
    ``<key>:<op>:<value>`` (e.g. ``row_count:gte:1000``).
    """
    query = build_search_query(
        q=q,
        tags=tag,
        require_all_tags=require_all_tags,
        keywords=keyword,
        mimetypes=mimetype,
        extensions=extension,
        min_size=min_size,
        max_size=max_size,
        actor_id=actor_id,
        folder_id=folder_id,
        recursive=recursive,
        created_after=created_after,
        created_before=created_before,
        kvs=kv,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    results = search_service.search_files(db, user=current_user, query=query)
    return FileSearchResponse(
        items=[FileRead.from_file(file) for file in results.items],
        total=results.total,
        limit=results.limit,
        offset=results.offset,
    )


@router.get("/facets")
async def file_facets(
    db: DbSession,
    current_user: CurrentUser,
    q: str | None = None,
    tag: list[str] = Query(default_factory=list),
    require_all_tags: bool = False,
    keyword: list[str] = Query(default_factory=list),
    mimetype: list[str] = Query(default_factory=list),
    extension: list[str] = Query(default_factory=list),
    min_size: int | None = None,
    max_size: int | None = None,
    actor_id: uuid.UUID | None = None,
    folder_id: uuid.UUID | None = None,
    recursive: bool = False,
    created_after: dt.datetime | None = None,
    created_before: dt.datetime | None = None,
    kv: list[str] = Query(default_factory=list),
    top: int = Query(
        default=SEARCH_DEFAULT_FACET_TOP,
        ge=1,
        le=SEARCH_MAX_FACET_TOP,
    ),
) -> FacetsRead:
    """Facet counts over the same query shape as `/search`.

    Each axis (tags, mimetypes, extensions) is computed with its own filter
    cleared so the panel keeps working as the user toggles values.
    """
    query = build_search_query(
        q=q,
        tags=tag,
        require_all_tags=require_all_tags,
        keywords=keyword,
        mimetypes=mimetype,
        extensions=extension,
        min_size=min_size,
        max_size=max_size,
        actor_id=actor_id,
        folder_id=folder_id,
        recursive=recursive,
        created_after=created_after,
        created_before=created_before,
        kvs=kv,
        sort="updated_at",
        order="desc",
        limit=SEARCH_DEFAULT_LIMIT,
        offset=0,
    )
    facets = search_service.compute_facets(
        db, user=current_user, query=query, top=top
    )
    return FacetsRead(
        tags=[
            FacetValueRead(value=item.value, count=item.count) for item in facets.tags
        ],
        mimetypes=[
            FacetValueRead(value=item.value, count=item.count)
            for item in facets.mimetypes
        ],
        extensions=[
            FacetValueRead(value=item.value, count=item.count)
            for item in facets.extensions
        ],
        kvs_keys=[
            FacetValueRead(value=item.value, count=item.count)
            for item in facets.kvs_keys
        ],
        total=facets.total,
    )


def build_search_query(
    *,
    q: str | None,
    tags: list[str],
    require_all_tags: bool,
    keywords: list[str],
    mimetypes: list[str],
    extensions: list[str],
    min_size: int | None,
    max_size: int | None,
    actor_id: uuid.UUID | None,
    folder_id: uuid.UUID | None,
    recursive: bool,
    created_after: dt.datetime | None,
    created_before: dt.datetime | None,
    kvs: list[str],
    sort: str,
    order: str,
    limit: int,
    offset: int,
) -> search_service.SearchQuery:
    return search_service.SearchQuery(
        q=q.strip() if q and q.strip() else None,
        tags=tuple(_dedupe(tags)),
        require_all_tags=require_all_tags,
        keywords=tuple(_dedupe(keywords)),
        mimetypes=tuple(_dedupe(mimetypes)),
        extensions=tuple(_dedupe(extensions)),
        min_size=min_size,
        max_size=max_size,
        actor_id=actor_id,
        folder_id=folder_id,
        recursive=recursive,
        created_after=created_after,
        created_before=created_before,
        kvs=tuple(search_service.KvsFilter.parse(item) for item in kvs),
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )


def _dedupe(values: list[str]) -> list[str]:
    """Trim, drop empties, dedupe case-insensitively while preserving first-seen casing."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        cleaned = raw.strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


@router.get("/{file_id}")
async def get_file(
    file_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> FileRead:
    return files_service.get_file(db, file_id, current_user)


@router.patch("/{file_id}/meta")
async def patch_file_meta(
    file_id: uuid.UUID,
    payload: PatchFileMetaRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> FileRead:
    """Deep-merge ``meta`` keys into the file's consumer-owned metadata."""
    file = files_service.patch_file_meta(
        db,
        file_id=file_id,
        patch=payload.meta,
        current_user=current_user,
    )
    return FileRead.from_file(file)


@router.patch("/{file_id}")
async def rename_file(
    file_id: uuid.UUID,
    payload: RenameFileRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> FileRead:
    """Rename a file in place."""
    file = files_service.rename_file(
        db,
        file_id=file_id,
        name=payload.name,
        current_user=current_user,
    )
    return FileRead.from_file(file)


@router.post("/{file_id}/move")
async def move_file(
    file_id: uuid.UUID,
    payload: MoveFileRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> FileRead:
    """Move a file to another folder. Atomic; refcount on Blob unchanged."""
    file = files_service.move_file(
        db,
        file_id=file_id,
        destination_folder_id=payload.destination_folder_id,
        name=payload.name,
        current_user=current_user,
    )
    return FileRead.from_file(file)

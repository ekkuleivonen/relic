import datetime as dt
import uuid

from fastapi import APIRouter, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies import CurrentUser, UnitOfWorkDep
from application.context import Actor
from application.control_plane.bulk_move_files import (
    bulk_move_files as bulk_move_files_use_case,
)
from application.control_plane.bulk_patch_file_meta import (
    bulk_patch_file_meta as bulk_patch_file_meta_use_case,
)
from application.control_plane.delete_file import (
    bulk_delete_files as bulk_delete_files_use_case,
    delete_file as delete_file_use_case,
)
from application.control_plane.move_file import move_file as move_file_use_case
from application.control_plane.patch_file_meta import (
    patch_file_meta as patch_file_meta_use_case,
)
from application.control_plane.rename_file import rename_file as rename_file_use_case
from constants import (
    FILESYSTEM_DEFAULT_LIST_LIMIT,
    FILESYSTEM_MAX_LIST_LIMIT,
    SEARCH_DEFAULT_FACET_TOP,
    SEARCH_DEFAULT_LIMIT,
    SEARCH_MAX_FACET_TOP,
    SEARCH_MAX_LIMIT,
)
from ports.entities import File
from application.control_plane.files import get_file as get_file_use_case
from application.control_plane import browse_filesystem
from domain.files.search import KvsFilter, SearchQuery
from application.control_plane.search_files import compute_facets, search_files

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


class BulkDeleteFilesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class BulkDeleteFilesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deleted_ids: list[uuid.UUID]
    errors: list[dict[str, str]]


class BulkMoveFilesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    destination_folder_id: uuid.UUID
    name: str | None = Field(default=None, min_length=1, max_length=255)


class BulkMoveFilesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    moved_ids: list[uuid.UUID]
    errors: list[dict[str, str]]


class BulkPatchFileMetaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    meta: dict = Field(default_factory=dict)


class BulkPatchFileMetaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patched_ids: list[uuid.UUID]
    errors: list[dict[str, str]]


@router.get("/")
async def list_files(
    uow: UnitOfWorkDep,
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
    page = browse_filesystem.list_files(
        uow,
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
async def search_files_route(
    uow: UnitOfWorkDep,
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
    results = search_files(uow, user=current_user, query=query)
    return FileSearchResponse(
        items=[FileRead.from_file(file) for file in results.items],
        total=results.total,
        limit=results.limit,
        offset=results.offset,
    )


@router.get("/facets")
async def file_facets(
    uow: UnitOfWorkDep,
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
    facets = compute_facets(uow, user=current_user, query=query, top=top)
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
) -> SearchQuery:
    return SearchQuery(
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
        kvs=tuple(KvsFilter.parse(item) for item in kvs),
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


@router.post("/bulk-delete")
async def bulk_delete_files(
    payload: BulkDeleteFilesRequest,
    uow: UnitOfWorkDep,
    current_user: CurrentUser,
) -> BulkDeleteFilesResponse:
    result = bulk_delete_files_use_case(
        uow,
        actor=Actor.from_user(current_user),
        file_ids=payload.file_ids,
    )
    return BulkDeleteFilesResponse(
        deleted_ids=result.deleted_ids,
        errors=result.errors,
    )


@router.post("/bulk-move")
async def bulk_move_files(
    payload: BulkMoveFilesRequest,
    uow: UnitOfWorkDep,
    current_user: CurrentUser,
) -> BulkMoveFilesResponse:
    result = bulk_move_files_use_case(
        uow,
        actor=Actor.from_user(current_user),
        file_ids=payload.file_ids,
        destination_folder_id=payload.destination_folder_id,
        name=payload.name,
    )
    return BulkMoveFilesResponse(
        moved_ids=result.moved_ids,
        errors=result.errors,
    )


@router.post("/bulk-update")
async def bulk_update_file_meta(
    payload: BulkPatchFileMetaRequest,
    uow: UnitOfWorkDep,
    current_user: CurrentUser,
) -> BulkPatchFileMetaResponse:
    result = bulk_patch_file_meta_use_case(
        uow,
        actor=Actor.from_user(current_user),
        file_ids=payload.file_ids,
        patch=payload.meta,
    )
    return BulkPatchFileMetaResponse(
        patched_ids=result.patched_ids,
        errors=result.errors,
    )


@router.get("/{file_id}")
async def get_file(
    file_id: uuid.UUID,
    uow: UnitOfWorkDep,
    current_user: CurrentUser,
) -> FileRead:
    file = get_file_use_case(
        uow,
        actor=Actor.from_user(current_user),
        file_id=file_id,
    )
    return FileRead.from_file(file)


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    file_id: uuid.UUID,
    uow: UnitOfWorkDep,
    current_user: CurrentUser,
) -> Response:
    delete_file_use_case(
        uow,
        actor=Actor.from_user(current_user),
        file_id=file_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{file_id}/meta")
async def patch_file_meta(
    file_id: uuid.UUID,
    payload: PatchFileMetaRequest,
    uow: UnitOfWorkDep,
    current_user: CurrentUser,
) -> FileRead:
    """Deep-merge ``meta`` keys into the file's consumer-owned metadata."""
    file = patch_file_meta_use_case(
        uow,
        actor=Actor.from_user(current_user),
        file_id=file_id,
        patch=payload.meta,
    )
    return FileRead.from_file(file)


@router.patch("/{file_id}")
async def rename_file(
    file_id: uuid.UUID,
    payload: RenameFileRequest,
    uow: UnitOfWorkDep,
    current_user: CurrentUser,
) -> FileRead:
    """Rename a file in place."""
    file = rename_file_use_case(
        uow,
        actor=Actor.from_user(current_user),
        file_id=file_id,
        name=payload.name,
    )
    return FileRead.from_file(file)


@router.post("/{file_id}/move")
async def move_file(
    file_id: uuid.UUID,
    payload: MoveFileRequest,
    uow: UnitOfWorkDep,
    current_user: CurrentUser,
) -> FileRead:
    """Move a file to another folder. Atomic; refcount on Blob unchanged."""
    file = move_file_use_case(
        uow,
        actor=Actor.from_user(current_user),
        file_id=file_id,
        destination_folder_id=payload.destination_folder_id,
        name=payload.name,
    )
    return FileRead.from_file(file)

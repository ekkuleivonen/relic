"""Admin routes for warm-path processors.

Processors are the warm-queue consumers that sit on top of the file-events
outbox. These routes let an admin browse cursor lag, pause/resume runs,
add or retire admin-managed processors (e.g. webhook sinks), and recover
from poisoned events via rewind/skip.
"""

import datetime as dt
import uuid

from fastapi import APIRouter, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from api.dependencies import AdminUser
from constants import PROCESSOR_DEFAULT_LIST_LIMIT, PROCESSOR_MAX_LIST_LIMIT
from database import DbSession
from models import Folder, Processor
from services import folder_access as folder_access_service
from services import processors as processor_service
from services.event_context import context_from_headers

router = APIRouter()


class ProcessorRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    name: str
    kind: str
    enabled: bool
    source: str
    subscribed_event_types: list[str]
    folder_scopes: list["ProcessorFolderScope"]
    mimetype_prefixes: list[str]
    extensions: list[str]
    config: dict
    last_committed_offset: int
    last_committed_at: dt.datetime | None
    last_failed_event_id: uuid.UUID | None
    last_failed_at: dt.datetime | None
    last_error_class: str | None
    last_error_message: str | None
    head_offset: int
    pending_count: int
    created_at: dt.datetime
    updated_at: dt.datetime

    @classmethod
    def from_lag(cls, item: processor_service.ProcessorWithLag) -> "ProcessorRead":
        processor = item.processor
        return cls(
            id=processor.id,
            name=processor.name,
            kind=processor.kind,
            enabled=processor.enabled,
            source=processor.source,
            subscribed_event_types=list(processor.subscribed_event_types),
            folder_scopes=[
                ProcessorFolderScope.model_validate(scope)
                for scope in processor.folder_scopes
            ],
            mimetype_prefixes=list(processor.mimetype_prefixes or []),
            extensions=list(processor.extensions or []),
            config=processor_service.public_processor_config(processor),
            last_committed_offset=int(processor.last_committed_offset),
            last_committed_at=processor.last_committed_at,
            last_failed_event_id=processor.last_failed_event_id,
            last_failed_at=processor.last_failed_at,
            last_error_class=processor.last_error_class,
            last_error_message=processor.last_error_message,
            head_offset=item.head_offset,
            pending_count=item.pending_count,
            created_at=processor.created_at,
            updated_at=processor.updated_at,
        )


class ProcessorListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ProcessorRead]
    total: int
    limit: int
    offset: int


class ProcessorEventTypeOptionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    label: str
    default: bool = False


class ProcessorMimetypeFilterOptionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    label: str
    default: bool = False


class ProcessorExtensionFilterOptionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    label: str
    default: bool = False


class ProcessorKindRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    display_name: str
    description: str
    default_task_queue: str
    default_concurrency: int
    max_concurrency: int
    default_subscribed_event_types: list[str]
    valid_event_types: list[str]
    event_type_options: list[ProcessorEventTypeOptionRead]
    default_mimetype_prefixes: list[str]
    valid_mimetype_prefixes: list[str]
    mimetype_filter_options: list[ProcessorMimetypeFilterOptionRead]
    default_extensions: list[str]
    valid_extensions: list[str]
    extension_filter_options: list[ProcessorExtensionFilterOptionRead]
    config_schema: dict


class ProcessorKindsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ProcessorKindRead]


class ProcessorFolderOptionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    name: str
    path: str


class ProcessorFolderOptionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ProcessorFolderOptionRead]


class ProcessorFolderScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    folder_id: uuid.UUID
    cascade: bool = False


class ProcessorCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    kind: str = Field(min_length=1, max_length=64)
    enabled: bool = True
    subscribed_event_types: list[str] | None = Field(default=None)
    folder_scopes: list[ProcessorFolderScope] | None = Field(default=None)
    mimetype_prefixes: list[str] | None = Field(default=None)
    extensions: list[str] | None = Field(default=None)
    config: dict | None = Field(default=None)


class ProcessorUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    subscribed_event_types: list[str] | None = None
    mimetype_prefixes: list[str] | None = None
    extensions: list[str] | None = None
    config: dict | None = None


class ProcessorRewindRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_offset: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=512)


class ProcessorSkipRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: uuid.UUID
    reason: str = Field(min_length=1, max_length=512)


@router.get("/")
async def list_processors_route(
    db: DbSession,
    limit: int = Query(
        default=PROCESSOR_DEFAULT_LIST_LIMIT,
        ge=1,
        le=PROCESSOR_MAX_LIST_LIMIT,
    ),
    offset: int = Query(default=0, ge=0),
) -> ProcessorListResponse:
    page = processor_service.list_processors(db, limit=limit, offset=offset)
    return ProcessorListResponse(
        items=[ProcessorRead.from_lag(item) for item in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/kinds")
async def list_processor_kinds_route() -> ProcessorKindsResponse:
    """Discover the processor kinds the running server supports.

    Useful for the admin UI when creating a new processor row.
    """
    return ProcessorKindsResponse(
        items=[
            ProcessorKindRead(
                kind=processor.kind,
                display_name=processor.display_name,
                description=processor.description,
                default_task_queue=processor.default_task_queue,
                default_concurrency=processor.default_concurrency,
                max_concurrency=processor.max_concurrency,
                default_subscribed_event_types=list(
                    processor.default_subscribed_event_types
                ),
                valid_event_types=list(processor.runtime_valid_event_types()),
                event_type_options=[
                    ProcessorEventTypeOptionRead.model_validate(
                        option.model_dump(mode="json")
                    )
                    for option in processor.event_type_options()
                ],
                default_mimetype_prefixes=list(processor.default_mimetype_prefixes),
                valid_mimetype_prefixes=list(processor.valid_mimetype_prefixes),
                mimetype_filter_options=[
                    ProcessorMimetypeFilterOptionRead.model_validate(
                        option.model_dump(mode="json")
                    )
                    for option in processor.mimetype_filter_options()
                ],
                default_extensions=list(processor.default_extensions),
                valid_extensions=list(processor.valid_extensions),
                extension_filter_options=[
                    ProcessorExtensionFilterOptionRead.model_validate(
                        option.model_dump(mode="json")
                    )
                    for option in processor.extension_filter_options()
                ],
                config_schema=processor.config_schema(),
            )
            for processor in processor_service.list_processor_definitions()
        ]
    )


@router.get("/folder-options")
async def list_processor_folder_options(db: DbSession) -> ProcessorFolderOptionsResponse:
    """Flat folder list for processor scope selectors."""
    folders = list(db.scalars(select(Folder)).all())
    paths = folder_access_service.compute_folder_paths(
        db,
        {folder.id for folder in folders},
    )
    return ProcessorFolderOptionsResponse(
        items=[
            ProcessorFolderOptionRead(
                id=folder.id,
                name=folder.name,
                path=paths[folder.id],
            )
            for folder in sorted(folders, key=lambda item: paths[item.id])
        ]
    )


@router.get("/{processor_id}")
async def get_processor_route(
    processor_id: uuid.UUID, db: DbSession
) -> ProcessorRead:
    item = processor_service.get_processor_with_lag(db, processor_id)
    return ProcessorRead.from_lag(item)


@router.post("/")
async def create_processor_route(
    payload: ProcessorCreateRequest,
    request: Request,
    db: DbSession,
    current_user: AdminUser,
) -> ProcessorRead:
    processor: Processor = processor_service.create_processor(
        db,
        name=payload.name,
        kind=payload.kind,
        enabled=payload.enabled,
        subscribed_event_types=payload.subscribed_event_types,
        folder_scopes=[
            scope.model_dump(mode="json") for scope in payload.folder_scopes
        ]
        if payload.folder_scopes is not None
        else None,
        mimetype_prefixes=payload.mimetype_prefixes,
        extensions=payload.extensions,
        config=payload.config,
        event_context=context_from_headers(
            request.headers, actor_id=current_user.id
        ),
    )
    item = processor_service.get_processor_with_lag(db, processor.id)
    return ProcessorRead.from_lag(item)


@router.patch("/{processor_id}")
async def update_processor_route(
    processor_id: uuid.UUID,
    payload: ProcessorUpdateRequest,
    request: Request,
    db: DbSession,
    current_user: AdminUser,
) -> ProcessorRead:
    processor_service.update_processor(
        db,
        processor_id=processor_id,
        enabled=payload.enabled,
        subscribed_event_types=payload.subscribed_event_types,
        mimetype_prefixes=payload.mimetype_prefixes,
        extensions=payload.extensions,
        config=payload.config,
        event_context=context_from_headers(
            request.headers, actor_id=current_user.id
        ),
    )
    item = processor_service.get_processor_with_lag(db, processor_id)
    return ProcessorRead.from_lag(item)


@router.delete("/{processor_id}")
async def delete_processor_route(
    processor_id: uuid.UUID, request: Request, db: DbSession, current_user: AdminUser
) -> Response:
    processor_service.delete_processor(
        db,
        processor_id=processor_id,
        event_context=context_from_headers(
            request.headers, actor_id=current_user.id
        ),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{processor_id}/rewind")
async def rewind_processor_route(
    processor_id: uuid.UUID,
    payload: ProcessorRewindRequest,
    request: Request,
    db: DbSession,
    current_user: AdminUser,
) -> ProcessorRead:
    processor_service.rewind_cursor(
        db,
        processor_id=processor_id,
        target_offset=payload.target_offset,
        reason=payload.reason,
        event_context=context_from_headers(
            request.headers, actor_id=current_user.id
        ),
    )
    item = processor_service.get_processor_with_lag(db, processor_id)
    return ProcessorRead.from_lag(item)


@router.post("/{processor_id}/skip")
async def skip_stuck_event_route(
    processor_id: uuid.UUID,
    payload: ProcessorSkipRequest,
    request: Request,
    db: DbSession,
    current_user: AdminUser,
) -> ProcessorRead:
    processor_service.skip_stuck_event(
        db,
        processor_id=processor_id,
        event_id=payload.event_id,
        reason=payload.reason,
        event_context=context_from_headers(
            request.headers, actor_id=current_user.id
        ),
    )
    item = processor_service.get_processor_with_lag(db, processor_id)
    return ProcessorRead.from_lag(item)

import datetime as dt
import uuid

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies import CurrentUser, UnitOfWorkDep
from application.control_plane import filesystem_events_queries
from constants import FILESYSTEM_EVENT_DEFAULT_LIMIT, FILESYSTEM_EVENT_MAX_LIMIT
from ports.entities import FilesystemEvent

router = APIRouter()


class FilesystemEventRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: int
    id: uuid.UUID
    event_type: str
    created_at: dt.datetime
    file_id: uuid.UUID | None
    folder_id: uuid.UUID
    actor_id: uuid.UUID | None
    request_id: str | None
    payload: dict

    @classmethod
    def from_event(cls, event: FilesystemEvent) -> "FilesystemEventRead":
        return cls(
            seq=event.seq,
            id=event.id,
            event_type=event.event_type,
            created_at=event.created_at,
            file_id=event.file_id,
            folder_id=event.folder_id,
            actor_id=event.actor_id,
            request_id=event.request_id,
            payload=dict(event.payload or {}),
        )


class FilesystemEventListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[FilesystemEventRead]
    cursor: int | None
    has_more: bool
    oldest_seq: int | None = Field(
        description="Earliest seq still retained; backfill via list/search if after is older."
    )


@router.get("/", summary="List filesystem events")
async def list_filesystem_events(
    uow: UnitOfWorkDep,
    current_user: CurrentUser,
    after: int = Query(default=0, ge=0),
    folder_id: uuid.UUID | None = None,
    recursive: bool = False,
    types: list[str] = Query(default_factory=list),
    limit: int = Query(
        default=FILESYSTEM_EVENT_DEFAULT_LIMIT,
        ge=1,
        le=FILESYSTEM_EVENT_MAX_LIMIT,
    ),
) -> FilesystemEventListResponse:
    """Poll integrator filesystem events with a monotonic seq cursor.

    Non-admin users only receive events for folders they can READ.
    """
    page = filesystem_events_queries.list_filesystem_events(
        uow,
        user=current_user,
        after=after,
        folder_id=folder_id,
        recursive=recursive,
        event_types=types or None,
        limit=limit,
    )

    return FilesystemEventListResponse(
        items=[FilesystemEventRead.from_event(event) for event in page.items],
        cursor=page.cursor,
        has_more=page.has_more,
        oldest_seq=page.oldest_seq,
    )

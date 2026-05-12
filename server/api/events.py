import datetime as dt
import uuid

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict

from api.users import UserRead
from database import DbSession
from models import Event
from services import events as event_service

router = APIRouter()


class EventRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    source: str
    operation: str
    status: str
    actor_user_id: uuid.UUID | None
    actor: UserRead | None
    request_id: str | None
    file_ids: list[str]
    folder_ids: list[str]
    blob_ids: list[str]
    metadata: dict
    created_at: dt.datetime
    updated_at: dt.datetime

    @classmethod
    def from_event(cls, event: Event) -> "EventRead":
        return cls(
            id=event.id,
            source=event.source,
            operation=event.operation,
            status=event.status,
            actor_user_id=event.actor_user_id,
            actor=UserRead.model_validate(event.actor) if event.actor else None,
            request_id=event.request_id,
            file_ids=event.file_ids,
            folder_ids=event.folder_ids,
            blob_ids=event.blob_ids,
            metadata=event.meta,
            created_at=event.created_at,
            updated_at=event.updated_at,
        )


class EventListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[EventRead]
    total: int
    limit: int
    offset: int


@router.get("/")
async def list_events(
    db: DbSession,
    source: str | None = None,
    operation: str | None = None,
    status: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    request_id: str | None = None,
    created_after: dt.datetime | None = None,
    created_before: dt.datetime | None = None,
    limit: int = Query(default=event_service.DEFAULT_LIMIT, ge=1, le=event_service.MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> EventListResponse:
    page = event_service.list_events(
        db,
        source=source,
        operation=operation,
        status=status,
        actor_user_id=actor_user_id,
        request_id=request_id,
        created_after=created_after,
        created_before=created_before,
        limit=limit,
        offset=offset,
    )
    return EventListResponse(
        items=[EventRead.from_event(event) for event in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )

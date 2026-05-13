import datetime as dt
import uuid

from fastapi import APIRouter, Query, Response, status
from pydantic import BaseModel, ConfigDict

from api.users import UserRead
from constants import FILE_EVENT_DEFAULT_LIMIT, FILE_EVENT_MAX_LIMIT
from database import DbSession
from models import FileEvent
from services import file_events as file_event_service

router = APIRouter()


class FileEventRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    offset: int
    schema_version: int
    event_type: str
    status: str
    actor_id: uuid.UUID | None
    actor: UserRead | None
    request_id: str | None
    idempotency_key: str | None
    file_id: uuid.UUID | None
    folder_id: uuid.UUID | None
    payload: dict
    created_at: dt.datetime

    @classmethod
    def from_event(cls, event: FileEvent) -> "FileEventRead":
        return cls(
            id=event.id,
            offset=event.offset,
            schema_version=event.schema_version,
            event_type=event.event_type,
            status=event.status,
            actor_id=event.actor_id,
            actor=UserRead.model_validate(event.actor) if event.actor else None,
            request_id=event.request_id,
            idempotency_key=event.idempotency_key,
            file_id=event.file_id,
            folder_id=event.folder_id,
            payload=event.payload,
            created_at=event.created_at,
        )


class FileEventListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[FileEventRead]
    total: int
    limit: int
    offset: int


@router.get("/")
async def list_file_events(
    db: DbSession,
    event_type: str | None = None,
    status: str | None = None,
    actor_id: uuid.UUID | None = None,
    request_id: str | None = None,
    file_id: uuid.UUID | None = None,
    folder_id: uuid.UUID | None = None,
    created_after: dt.datetime | None = None,
    created_before: dt.datetime | None = None,
    limit: int = Query(
        default=FILE_EVENT_DEFAULT_LIMIT,
        ge=1,
        le=FILE_EVENT_MAX_LIMIT,
    ),
    offset: int = Query(default=0, ge=0),
) -> FileEventListResponse:
    page = file_event_service.list_file_events(
        db,
        event_type=event_type,
        status=status,
        actor_id=actor_id,
        request_id=request_id,
        file_id=file_id,
        folder_id=folder_id,
        created_after=created_after,
        created_before=created_before,
        limit=limit,
        offset=offset,
    )
    return FileEventListResponse(
        items=[FileEventRead.from_event(event) for event in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.delete("/")
async def clear_file_events(db: DbSession) -> Response:
    file_event_service.clear_file_events(db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

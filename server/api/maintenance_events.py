import datetime as dt
import uuid

from fastapi import APIRouter, Query, Response, status
from pydantic import BaseModel, ConfigDict

from constants import MAINTENANCE_EVENT_DEFAULT_LIMIT, MAINTENANCE_EVENT_MAX_LIMIT
from database import DbSession
from models import MaintenanceEvent
from services import maintenance_events as maintenance_event_service

router = APIRouter()


class MaintenanceEventRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    job: str
    action: str
    status: str
    batch_id: uuid.UUID
    bucket_id: uuid.UUID | None
    blob_id: uuid.UUID | None
    duration_ms: int | None
    metadata: dict
    created_at: dt.datetime

    @classmethod
    def from_event(cls, event: MaintenanceEvent) -> "MaintenanceEventRead":
        return cls(
            id=event.id,
            job=event.job,
            action=event.action,
            status=event.status,
            batch_id=event.batch_id,
            bucket_id=event.bucket_id,
            blob_id=event.blob_id,
            duration_ms=event.duration_ms,
            metadata=event.meta,
            created_at=event.created_at,
        )


class MaintenanceEventListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[MaintenanceEventRead]
    total: int
    limit: int
    offset: int


@router.get("/")
async def list_maintenance_events(
    db: DbSession,
    job: str | None = None,
    action: str | None = None,
    status: str | None = None,
    batch_id: uuid.UUID | None = None,
    bucket_id: uuid.UUID | None = None,
    blob_id: uuid.UUID | None = None,
    created_after: dt.datetime | None = None,
    created_before: dt.datetime | None = None,
    limit: int = Query(
        default=MAINTENANCE_EVENT_DEFAULT_LIMIT,
        ge=1,
        le=MAINTENANCE_EVENT_MAX_LIMIT,
    ),
    offset: int = Query(default=0, ge=0),
) -> MaintenanceEventListResponse:
    page = maintenance_event_service.list_maintenance_events(
        db,
        job=job,
        action=action,
        status=status,
        batch_id=batch_id,
        bucket_id=bucket_id,
        blob_id=blob_id,
        created_after=created_after,
        created_before=created_before,
        limit=limit,
        offset=offset,
    )
    return MaintenanceEventListResponse(
        items=[MaintenanceEventRead.from_event(event) for event in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.delete("/")
async def clear_maintenance_events(db: DbSession) -> Response:
    maintenance_event_service.clear_maintenance_events(db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

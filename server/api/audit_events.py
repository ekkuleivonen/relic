import datetime as dt
import uuid

from fastapi import APIRouter, Query, Response, status
from pydantic import BaseModel, ConfigDict

from api.users import UserRead
from api.dependencies import AdminUser, UnitOfWorkDep
from application.control_plane.audit_mutations import (
    clear_audit_events as clear_audit_events_use_case,
)
from constants import AUDIT_EVENT_DEFAULT_LIMIT, AUDIT_EVENT_MAX_LIMIT
from infra.db.models import AuditEvent
from application.control_plane import audit_events

router = APIRouter()


class AuditEventRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    operation: str
    status: str
    actor_id: uuid.UUID | None
    actor: UserRead | None
    request_id: str | None
    job: str | None
    batch_id: uuid.UUID | None
    bucket_id: uuid.UUID | None
    blob_id: uuid.UUID | None
    duration_ms: int | None
    metadata: dict
    created_at: dt.datetime
    updated_at: dt.datetime

    @classmethod
    def from_event(cls, event: AuditEvent) -> "AuditEventRead":
        return cls(
            id=event.id,
            operation=event.operation,
            status=event.status,
            actor_id=event.actor_id,
            actor=UserRead.model_validate(event.actor) if event.actor else None,
            request_id=event.request_id,
            job=event.job,
            batch_id=event.batch_id,
            bucket_id=event.bucket_id,
            blob_id=event.blob_id,
            duration_ms=event.duration_ms,
            metadata=event.meta,
            created_at=event.created_at,
            updated_at=event.updated_at,
        )


class AuditEventListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AuditEventRead]
    total: int
    limit: int
    offset: int


@router.get("/")
async def list_audit_events(
    uow: UnitOfWorkDep,
    operation: str | None = None,
    status: str | None = None,
    actor_id: uuid.UUID | None = None,
    request_id: str | None = None,
    job: str | None = None,
    batch_id: uuid.UUID | None = None,
    bucket_id: uuid.UUID | None = None,
    blob_id: uuid.UUID | None = None,
    created_after: dt.datetime | None = None,
    created_before: dt.datetime | None = None,
    limit: int = Query(
        default=AUDIT_EVENT_DEFAULT_LIMIT,
        ge=1,
        le=AUDIT_EVENT_MAX_LIMIT,
    ),
    offset: int = Query(default=0, ge=0),
) -> AuditEventListResponse:
    page = audit_events.list_audit_events(
        uow.session,
        operation=operation,
        status=status,
        actor_id=actor_id,
        request_id=request_id,
        job=job,
        batch_id=batch_id,
        bucket_id=bucket_id,
        blob_id=blob_id,
        created_after=created_after,
        created_before=created_before,
        limit=limit,
        offset=offset,
    )
    return AuditEventListResponse(
        items=[AuditEventRead.from_event(event) for event in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.delete("/")
async def clear_audit_events(uow: UnitOfWorkDep, current_user: AdminUser) -> Response:
    clear_audit_events_use_case(uow)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

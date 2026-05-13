import datetime as dt
import uuid

from fastapi import APIRouter, Query, Response, status
from pydantic import BaseModel, ConfigDict

from api.users import UserRead
from database import DbSession
from models import AuditEvent
from services import audit_events as audit_event_service

router = APIRouter()


class AuditEventRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    operation: str
    status: str
    actor_user_id: uuid.UUID | None
    actor: UserRead | None
    request_id: str | None
    metadata: dict
    created_at: dt.datetime
    updated_at: dt.datetime

    @classmethod
    def from_event(cls, event: AuditEvent) -> "AuditEventRead":
        return cls(
            id=event.id,
            operation=event.operation,
            status=event.status,
            actor_user_id=event.actor_user_id,
            actor=UserRead.model_validate(event.actor) if event.actor else None,
            request_id=event.request_id,
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
    db: DbSession,
    operation: str | None = None,
    status: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    request_id: str | None = None,
    created_after: dt.datetime | None = None,
    created_before: dt.datetime | None = None,
    limit: int = Query(
        default=audit_event_service.DEFAULT_LIMIT,
        ge=1,
        le=audit_event_service.MAX_LIMIT,
    ),
    offset: int = Query(default=0, ge=0),
) -> AuditEventListResponse:
    page = audit_event_service.list_audit_events(
        db,
        operation=operation,
        status=status,
        actor_user_id=actor_user_id,
        request_id=request_id,
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
async def clear_audit_events(db: DbSession) -> Response:
    audit_event_service.clear_audit_events(db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

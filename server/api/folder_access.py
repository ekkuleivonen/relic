import datetime as dt
import uuid

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies import AdminUser, UnitOfWorkDep
from api.users import UserRead
from application.context import context_from_headers
from application.control_plane.grant_folder_access import (
    grant_folder_access as grant_folder_access_use_case,
    revoke_folder_access as revoke_folder_access_use_case,
)
from application.control_plane.list_folder_access import list_folder_access as list_folder_access_use_case
from infra.db.stores.folder_access_types import FolderAccessRow

router = APIRouter()


class FolderAccessGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: uuid.UUID = Field(description="User receiving the grant.")
    folder_id: uuid.UUID = Field(description="Folder the grant applies to.")
    permissions: int = Field(
        gt=0,
        description=(
            "Permission bitfield: READ=1, WRITE=2, DELETE=4, ENRICH=8. "
            "Combine with bitwise OR. Inherits to descendant folders."
        ),
    )


class FolderAccessRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    user: UserRead
    folder_id: uuid.UUID
    folder_path: str
    permissions: int
    created_at: dt.datetime
    updated_at: dt.datetime

    @classmethod
    def from_row(cls, row: FolderAccessRow) -> "FolderAccessRead":
        return cls(
            id=row.access.id,
            user=UserRead.model_validate(row.user),
            folder_id=row.access.folder_id,
            folder_path=row.folder_path,
            permissions=row.access.permissions,
            created_at=row.access.created_at,
            updated_at=row.access.updated_at,
        )


@router.get("/", summary="List folder access grants")
async def list_folder_access(uow: UnitOfWorkDep) -> list[FolderAccessRead]:
    """List all explicit folder grants with resolved paths. Admin only."""
    rows = list_folder_access_use_case(uow)
    return [FolderAccessRead.from_row(row) for row in rows]


@router.post("/", summary="Grant folder access")
async def create_folder_access(
    payload: FolderAccessGrant,
    request: Request,
    uow: UnitOfWorkDep,
    current_user: AdminUser,
) -> FolderAccessRead:
    """Grant or update permissions on a folder. Idempotent per (actor, folder). Admin only."""
    row = grant_folder_access_use_case(
        uow,
        actor_id=payload.actor_id,
        folder_id=payload.folder_id,
        permissions=payload.permissions,
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )
    return FolderAccessRead.from_row(row)


@router.delete("/{access_id}", summary="Revoke folder access")
async def delete_folder_access(
    access_id: uuid.UUID,
    request: Request,
    uow: UnitOfWorkDep,
    current_user: AdminUser,
) -> Response:
    """Revoke an explicit grant. Inherited ancestor permissions remain. Admin only."""
    revoke_folder_access_use_case(
        uow,
        access_id=access_id,
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

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
from application.control_plane.folder_access import FolderAccessRow
from infra.db.engine import DbSession
from application.control_plane import folder_access

router = APIRouter()

"""
Folder access management. Admin-only.

A FolderAccess row grants an actor permissions on a folder; permissions
recurse to descendant folders. There is one row per (actor, folder).
"""


class FolderAccessGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: uuid.UUID
    folder_id: uuid.UUID
    permissions: int = Field(gt=0)


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


@router.get("/")
async def list_folder_access(db: DbSession) -> list[FolderAccessRead]:
    """
    GET /folder-access -> all grants across the filesystem.
    Returns a flat list with embedded user info and resolved folder paths.
    """
    rows = folder_access.list_folder_access(db)
    return [FolderAccessRead.from_row(row) for row in rows]


@router.post("/")
async def create_folder_access(
    payload: FolderAccessGrant,
    request: Request,
    uow: UnitOfWorkDep,
    current_user: AdminUser,
) -> FolderAccessRead:
    """
    POST /folder-access -> grant a user permissions on a folder.
    Body: { actor_id, folder_id, permissions }
    Idempotent: an existing row for the same (actor, folder) is updated.
    """
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


@router.delete("/{access_id}")
async def delete_folder_access(
    access_id: uuid.UUID,
    request: Request,
    uow: UnitOfWorkDep,
    current_user: AdminUser,
) -> Response:
    """
    DELETE /folder-access/{access_id} -> revoke an explicit grant.
    Inherited permissions from ancestor folders remain in effect.
    """
    revoke_folder_access_use_case(
        uow,
        access_id=access_id,
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

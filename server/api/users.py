import datetime as dt
import uuid

from api.dependencies import AdminUser, UnitOfWorkDep
from application.context import context_from_headers
from application.control_plane import users
from application.control_plane.user_mutations import (
    create_user as create_user_use_case,
    delete_user as delete_user_use_case,
    update_user as update_user_use_case,
)
from enums import UserRole
from fastapi import APIRouter, Request, Response, status
from infra.db.engine import DbSession
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter()

"""
User management. Admin-only for create/delete/list; users can read and
update their own record.

Auth model is intentionally minimal for now (password hash on User).
Swap to OIDC/Authentik later by replacing the auth dependency, not these
routes.
"""


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+$")
    password: str = Field(min_length=8)
    role: UserRole


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = Field(
        default=None, min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+$"
    )
    password: str | None = Field(default=None, min_length=8)
    role: UserRole | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    name: str
    email: str
    role: UserRole
    created_at: dt.datetime
    updated_at: dt.datetime


@router.get("/")
async def list_users(request: Request, db: DbSession) -> list[UserRead]:
    """
    GET /users -> list all users. Admin-only.
    Query params: ?limit=50&cursor=<id>&role=<int>
    """
    return users.list_users(db)


@router.post("/")
async def create_user(
    request: Request,
    payload: UserCreate,
    uow: UnitOfWorkDep,
    current_user: AdminUser,
) -> UserRead:
    """
    POST /users -> create a new user. Admin-only.
    Body: { name, email, password, role }
    Returns the created User without password_hash.
    """
    return create_user_use_case(
        uow,
        payload.model_dump(),
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )


@router.get("/{user_id}")
async def get_user(user_id: uuid.UUID, request: Request, db: DbSession) -> UserRead:
    """
    GET /users/{id} -> fetch a single user.
    Self or admin only.
    """
    return users.get_user(db, user_id)


@router.patch("/{user_id}")
async def update_user(
    user_id: uuid.UUID,
    request: Request,
    payload: UserUpdate,
    uow: UnitOfWorkDep,
    current_user: AdminUser,
) -> UserRead:
    """
    PATCH /users/{id} -> update mutable fields.
    Body: { name?, email?, role?, password? }
    Self can update name/email/password; only admin can change role.
    """
    return update_user_use_case(
        uow,
        user_id,
        payload.model_dump(exclude_unset=True),
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )


@router.delete("/{user_id}")
async def delete_user(
    user_id: uuid.UUID,
    request: Request,
    uow: UnitOfWorkDep,
    current_user: AdminUser,
) -> Response:
    """
    DELETE /users/{id} -> hard delete. Admin-only.
    Cascades: revoke all access keys, drop folder access rows.
    Users with uploaded files cannot be deleted.
    """
    delete_user_use_case(
        uow,
        user_id,
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

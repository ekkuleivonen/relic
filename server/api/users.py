import datetime as dt
import uuid

from database import DbSession
from enums import UserRole
from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from services import users as user_service
from services.event_context import context_from_headers

from api.dependencies import AdminUser

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
    return user_service.list_users(db)


@router.post("/")
async def create_user(
    request: Request, payload: UserCreate, db: DbSession, current_user: AdminUser
) -> UserRead:
    """
    POST /users -> create a new user. Admin-only.
    Body: { name, email, password, role }
    Returns the created User without password_hash.
    """
    return user_service.create_user(
        db,
        payload.model_dump(),
        event_context=context_from_headers(
            request.headers,
            actor_user_id=current_user.id,
        ),
    )


@router.get("/{user_id}")
async def get_user(user_id: uuid.UUID, request: Request, db: DbSession) -> UserRead:
    """
    GET /users/{id} -> fetch a single user.
    Self or admin only.
    """
    return user_service.get_user(db, user_id)


@router.patch("/{user_id}")
async def update_user(
    user_id: uuid.UUID,
    request: Request,
    payload: UserUpdate,
    db: DbSession,
    current_user: AdminUser,
) -> UserRead:
    """
    PATCH /users/{id} -> update mutable fields.
    Body: { name?, email?, role?, password? }
    Self can update name/email/password; only admin can change role.
    """
    return user_service.update_user(
        db,
        user_id,
        payload.model_dump(exclude_unset=True),
        event_context=context_from_headers(
            request.headers,
            actor_user_id=current_user.id,
        ),
    )


@router.delete("/{user_id}")
async def delete_user(
    user_id: uuid.UUID, request: Request, db: DbSession, current_user: AdminUser
) -> Response:
    """
    DELETE /users/{id} -> hard delete. Admin-only.
    Cascades: revoke all access keys, drop folder access rows.
    Users with uploaded files cannot be deleted.
    """
    user_service.delete_user(
        db,
        user_id,
        event_context=context_from_headers(
            request.headers,
            actor_user_id=current_user.id,
        ),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

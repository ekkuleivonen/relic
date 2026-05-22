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
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter()


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255, description="Display name.")
    email: str = Field(
        min_length=3,
        max_length=320,
        pattern=r"^[^@\s]+@[^@\s]+$",
        description="Unique login email.",
    )
    password: str = Field(min_length=8, description="Initial password (min 8 characters).")
    role: UserRole = Field(description="Account role (`admin` or `user`).")


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = Field(
        default=None, min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+$"
    )
    password: str | None = Field(default=None, min_length=8)
    role: UserRole | None = Field(
        default=None, description="Only admins may change role."
    )


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    name: str
    email: str
    role: UserRole
    created_at: dt.datetime
    updated_at: dt.datetime


@router.get("/", summary="List users")
async def list_users(request: Request, uow: UnitOfWorkDep) -> list[UserRead]:
    """List all users. Admin only."""
    return users.list_users(uow)


@router.post("/", summary="Create user")
async def create_user(
    request: Request,
    payload: UserCreate,
    uow: UnitOfWorkDep,
    current_user: AdminUser,
) -> UserRead:
    """Create a new user. Admin only. Password hash is never returned."""
    return create_user_use_case(
        uow,
        payload.model_dump(),
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )


@router.get("/{user_id}", summary="Get user")
async def get_user(user_id: uuid.UUID, request: Request, uow: UnitOfWorkDep) -> UserRead:
    """Fetch a single user. Self or admin."""
    return users.get_user(uow, user_id)


@router.patch("/{user_id}", summary="Update user")
async def update_user(
    user_id: uuid.UUID,
    request: Request,
    payload: UserUpdate,
    uow: UnitOfWorkDep,
    current_user: AdminUser,
) -> UserRead:
    """Update mutable fields. Self may change name/email/password; only admin may change role."""
    return update_user_use_case(
        uow,
        user_id,
        payload.model_dump(exclude_unset=True),
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )


@router.delete("/{user_id}", summary="Delete user")
async def delete_user(
    user_id: uuid.UUID,
    request: Request,
    uow: UnitOfWorkDep,
    current_user: AdminUser,
) -> Response:
    """
    Hard delete a user. Admin only. Revokes access keys and folder grants.
    Refuses if the user has uploaded files.
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

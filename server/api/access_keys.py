import datetime as dt
import uuid

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies import AdminUser, UnitOfWorkDep
from api.users import UserRead
from application.context import context_from_headers
from application.control_plane.access_keys_queries import (
    get_access_key_by_key_id as get_access_key_by_key_id_use_case,
    list_access_keys as list_access_keys_use_case,
)
from application.control_plane.access_key_mutations import (
    create_access_key as create_access_key_use_case,
    delete_access_key as delete_access_key_use_case,
    revoke_access_key as revoke_access_key_use_case,
)
from infra.db.stores.access_keys import AccessKeyRow, CreatedAccessKey

router = APIRouter()


class AccessKeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: uuid.UUID = Field(
        description="User the key acts as (inherits their folder permissions)."
    )
    name: str = Field(min_length=1, max_length=255, description="Human-readable label.")


class AccessKeyRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    user: UserRead
    name: str
    key_id: str
    last_used_at: dt.datetime | None
    revoked_at: dt.datetime | None
    created_at: dt.datetime
    updated_at: dt.datetime

    @classmethod
    def from_row(cls, row: AccessKeyRow) -> "AccessKeyRead":
        return cls(
            id=row.access_key.id,
            user=UserRead.model_validate(row.user),
            name=row.access_key.name,
            key_id=row.access_key.key_id,
            last_used_at=row.access_key.last_used_at,
            revoked_at=row.access_key.revoked_at,
            created_at=row.access_key.created_at,
            updated_at=row.access_key.updated_at,
        )


class AccessKeyCreated(AccessKeyRead):
    secret_access_key: str = Field(
        description="Shown once at creation. Use as `Bearer key_id:secret` for `/api/*`."
    )

    @classmethod
    def from_created(cls, created: CreatedAccessKey) -> "AccessKeyCreated":
        row = created.row
        return cls(
            id=row.access_key.id,
            user=UserRead.model_validate(row.user),
            name=row.access_key.name,
            key_id=row.access_key.key_id,
            secret_access_key=created.secret_access_key,
            last_used_at=row.access_key.last_used_at,
            revoked_at=row.access_key.revoked_at,
            created_at=row.access_key.created_at,
            updated_at=row.access_key.updated_at,
        )


@router.get("/", summary="List access keys")
async def list_access_keys(uow: UnitOfWorkDep) -> list[AccessKeyRead]:
    """List access keys. Admins see all; users see their own. Secret never returned."""
    return [AccessKeyRead.from_row(row) for row in list_access_keys_use_case(uow)]


@router.post("/", summary="Create access key")
async def create_access_key(
    payload: AccessKeyCreate,
    request: Request,
    uow: UnitOfWorkDep,
    current_user: AdminUser,
) -> AccessKeyCreated:
    """
    Mint a new access key. Admin only.
    The `secret_access_key` is returned once and cannot be retrieved later.
    """
    created = create_access_key_use_case(
        uow,
        actor_id=payload.actor_id,
        name=payload.name,
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )
    return AccessKeyCreated.from_created(created)


@router.get("/{key_id}", summary="Get access key")
async def get_access_key(key_id: str, uow: UnitOfWorkDep) -> AccessKeyRead:
    """Fetch metadata for one key. Self or admin. Secret never included."""
    return AccessKeyRead.from_row(get_access_key_by_key_id_use_case(uow, key_id))


@router.post("/{key_id}/revoke", summary="Revoke access key")
async def revoke_access_key(
    key_id: str,
    request: Request,
    uow: UnitOfWorkDep,
    current_user: AdminUser,
) -> AccessKeyRead:
    """Set `revoked_at`. Idempotent. Revoked keys are kept for audit."""
    row = revoke_access_key_use_case(
        uow,
        key_id,
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )
    return AccessKeyRead.from_row(row)


@router.delete("/{key_id}", summary="Delete access key")
async def delete_access_key(
    key_id: str,
    request: Request,
    uow: UnitOfWorkDep,
    current_user: AdminUser,
) -> Response:
    """Hard delete a key row. Self for own keys; admin for any."""
    delete_access_key_use_case(
        uow,
        key_id,
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

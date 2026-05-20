import datetime as dt
import uuid

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies import AdminUser, UnitOfWorkDep
from api.users import UserRead
from application.context import context_from_headers
from application.control_plane import access_keys
from application.control_plane.access_key_mutations import (
    create_access_key as create_access_key_use_case,
    delete_access_key as delete_access_key_use_case,
    revoke_access_key as revoke_access_key_use_case,
)
from application.control_plane.access_keys import AccessKeyRow, CreatedAccessKey
from infra.db.engine import DbSession

router = APIRouter()

"""
S3 access keys. Each key belongs to a user and inherits that user's
folder permissions for SigV4-authenticated requests at the S3 gateway.

Secret is shown ONCE at creation, then only the hash is stored.
"""


class AccessKeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)


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
    secret_access_key: str

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


@router.get("/")
async def list_access_keys(db: DbSession) -> list[AccessKeyRead]:
    """
    GET /access-keys -> list keys.
    Self sees own keys; admin sees all.
    Never returns the secret, only key_id, name, last_used_at, revoked_at.
    """
    return [AccessKeyRead.from_row(row) for row in access_keys.list_access_keys(db)]


@router.post("/")
async def create_access_key(
    payload: AccessKeyCreate,
    request: Request,
    uow: UnitOfWorkDep,
    current_user: AdminUser,
) -> AccessKeyCreated:
    """
    POST /access-keys -> mint a new access key.
    Body: { name, actor_id }
    Returns: { id, key_id, secret_access_key, name, ... }
    The secret is in the response body and CANNOT be retrieved later.
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


@router.get("/{key_id}")
async def get_access_key(key_id: str, db: DbSession) -> AccessKeyRead:
    """
    GET /access-keys/{id} -> metadata for one key.
    Self for own; admin for any. Secret never included.
    """
    return AccessKeyRead.from_row(access_keys.get_access_key_by_key_id(db, key_id))


@router.post("/{key_id}/revoke")
async def revoke_access_key(
    key_id: str,
    request: Request,
    uow: UnitOfWorkDep,
    current_user: AdminUser,
) -> AccessKeyRead:
    """
    POST /access-keys/{id}/revoke -> set revoked_at to now.
    Idempotent. Revoked keys are kept for audit; use DELETE to remove.
    """
    row = revoke_access_key_use_case(
        uow,
        key_id,
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )
    return AccessKeyRead.from_row(row)


@router.delete("/{key_id}")
async def delete_access_key(
    key_id: str,
    request: Request,
    uow: UnitOfWorkDep,
    current_user: AdminUser,
) -> Response:
    """
    DELETE /access-keys/{id} -> hard delete the key row.
    Self for own; admin for any.
    """
    delete_access_key_use_case(
        uow,
        key_id,
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

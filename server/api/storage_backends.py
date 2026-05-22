import datetime as dt
import uuid

from api.dependencies import AdminUser, UnitOfWorkDep
from application.context import context_from_headers
from application.control_plane import storage_backends
from application.control_plane.storage_backend_mutations import (
    create_storage_backend as create_storage_backend_use_case,
    delete_storage_backend as delete_storage_backend_use_case,
    probe_storage_backend as probe_storage_backend_use_case,
    update_storage_backend as update_storage_backend_use_case,
)
from application.control_plane.drain_storage_backend import drain_storage_backend as drain_storage_backend_use_case
from domain.exceptions import BadRequestError
from enums import StorageBackendKind
from fastapi import APIRouter, Query, Request, Response, status
from infra.db.models import StorageBackendProbe
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import desc, select

router = APIRouter()

"""
StorageBackend backend management. Admin-only across the board - buckets are
infrastructure, not user data.

The access credentials are encrypted at rest with settings.ENCRYPTION_SECRET.
Read responses return masked key identifiers and never return decrypted secrets;
supply new credentials via POST/PATCH when rotating.

There is no static "tier" anymore. Placement ranks buckets by their recent
probe latency (see infra.db.stores.placement.hotness_ranked_storage_backends) and the cron
job rebalances blobs based on access patterns + bucket pressure.
"""


def _require_absolute_filesystem_path(endpoint: str) -> None:
    if not endpoint.startswith("/"):
        raise ValueError("Filesystem base path must be an absolute path")


class StorageBackendCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    endpoint: str = Field(min_length=1)
    region: str | None = Field(default=None, min_length=1, max_length=128)
    namespace: str = Field(min_length=1, max_length=255)
    key_id: str | None = Field(default=None, min_length=1)
    secret_access_key: str | None = Field(default=None, min_length=1)
    max_size_bytes: int = Field(gt=0)
    kind: StorageBackendKind = StorageBackendKind.S3

    @model_validator(mode="after")
    def validate_kind_fields(self) -> "StorageBackendCreate":
        if self.kind == StorageBackendKind.FILESYSTEM:
            _require_absolute_filesystem_path(self.endpoint)
            self.region = self.region or "local"
            self.key_id = self.key_id or "filesystem"
            self.secret_access_key = self.secret_access_key or "filesystem"
            return self

        if not self.region:
            raise ValueError("region is required for S3 storage backends")
        if not self.key_id:
            raise ValueError("key_id is required for S3 storage backends")
        if not self.secret_access_key:
            raise ValueError("secret_access_key is required for S3 storage backends")
        return self


class StorageBackendUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    endpoint: str | None = Field(default=None, min_length=1)
    region: str | None = Field(default=None, min_length=1, max_length=128)
    namespace: str | None = Field(default=None, min_length=1, max_length=255)
    max_size_bytes: int | None = Field(default=None, gt=0)
    key_id: str | None = Field(default=None, min_length=1)
    secret_access_key: str | None = Field(default=None, min_length=1)
    kind: StorageBackendKind | None = None


class StorageBackendRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    name: str
    endpoint: str
    region: str
    namespace: str
    key_id: str
    secret_access_key: str = Field(
        description="Always masked on read; write-only via create/update payloads."
    )
    max_size_bytes: int
    kind: StorageBackendKind
    object_count: int
    current_size_bytes: int
    avg_latency_ms: float | None
    probe_sample_count: int
    reachable: bool


class StorageBackendProbeRead(StorageBackendRead):
    pass


class StorageBackendProbeSample(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    observed_at: dt.datetime
    success: bool
    put_ms: int | None
    head_ms: int | None
    get_ms: int | None
    delete_ms: int | None


@router.get("/", summary="List storage backends")
async def list_storage_backends(request: Request, uow: UnitOfWorkDep) -> list[StorageBackendRead]:
    """List configured blob backends with usage and probe latency. Admin only."""
    return storage_backends.list_storage_backend_reads(uow)


@router.post("/", summary="Create storage backend")
async def create_storage_backend(
    request: Request,
    payload: StorageBackendCreate,
    uow: UnitOfWorkDep,
    current_user: AdminUser,
) -> StorageBackendRead:
    """Register a new S3 or filesystem blob backend. Admin only."""
    bucket = create_storage_backend_use_case(
        uow,
        payload.model_dump(),
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )
    return storage_backends.get_storage_backend_read(uow, bucket.id)


@router.get("/{storage_backend_id}", summary="Get storage backend")
async def get_storage_backend(
    storage_backend_id: uuid.UUID, request: Request, uow: UnitOfWorkDep
) -> StorageBackendRead:
    """Fetch one backend with usage and rolling-average latency. Admin only."""
    return storage_backends.get_storage_backend_read(uow, storage_backend_id)


@router.patch("/{storage_backend_id}", summary="Update storage backend")
async def update_storage_backend(
    storage_backend_id: uuid.UUID,
    request: Request,
    payload: StorageBackendUpdate,
    uow: UnitOfWorkDep,
    current_user: AdminUser,
) -> StorageBackendRead:
    """Update mutable backend fields. Admin only."""
    existing = storage_backends.get_storage_backend(uow, storage_backend_id)
    values = payload.model_dump(exclude_unset=True)

    if payload.kind is not None and payload.kind != existing.kind:
        raise BadRequestError("Cannot change storage backend kind after creation")

    if existing.kind == StorageBackendKind.FILESYSTEM:
        values.pop("key_id", None)
        values.pop("secret_access_key", None)
        values.pop("region", None)
        if "endpoint" in values:
            _require_absolute_filesystem_path(values["endpoint"])

    update_storage_backend_use_case(
        uow,
        storage_backend_id,
        values,
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )
    return storage_backends.get_storage_backend_read(uow, storage_backend_id)


@router.delete("/{storage_backend_id}", summary="Delete storage backend")
async def delete_storage_backend(
    storage_backend_id: uuid.UUID,
    request: Request,
    uow: UnitOfWorkDep,
    current_user: AdminUser,
) -> Response:
    """
    Remove a backend. Refuses if blobs still reference it (409 with count).
    Admin only.
    """
    delete_storage_backend_use_case(
        uow,
        storage_backend_id,
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{storage_backend_id}/probe", summary="Probe storage backend")
async def probe_storage_backend(
    storage_backend_id: uuid.UUID,
    request: Request,
    uow: UnitOfWorkDep,
    current_user: AdminUser,
) -> StorageBackendProbeRead:
    """
    Run PUT/HEAD/GET/DELETE probes and record latency sample. Admin only.
    """
    probe_storage_backend_use_case(uow, storage_backend_id)
    return StorageBackendProbeRead(**storage_backends.get_storage_backend_read(uow, storage_backend_id))


class DrainStorageBackendResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    moved: int
    skipped: int
    failed: int
    scanned: int


@router.post("/{storage_backend_id}/drain", summary="Drain storage backend")
async def drain_storage_backend(
    storage_backend_id: uuid.UUID,
    request: Request,
    uow: UnitOfWorkDep,
    current_user: AdminUser,
) -> DrainStorageBackendResponse:
    """Migrate all blobs to other backends with capacity. Admin only."""
    result = drain_storage_backend_use_case(
        uow,
        storage_backend_id=storage_backend_id,
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )
    return DrainStorageBackendResponse(
        moved=result["moved"],
        skipped=result["skipped"],
        failed=result["failed"],
        scanned=result["scanned"],
    )


@router.get("/{storage_backend_id}/probes", summary="List probe samples")
async def list_storage_backend_probes(
    storage_backend_id: uuid.UUID,
    request: Request,
    uow: UnitOfWorkDep,
    current_user: AdminUser,
    limit: int = Query(default=20, ge=1, le=200),
) -> list[StorageBackendProbeSample]:
    """Recent probe samples for a backend, newest first. Admin only."""
    storage_backends.get_storage_backend(uow, storage_backend_id)
    rows = list(
        uow.session.scalars(
            select(StorageBackendProbe)
            .where(StorageBackendProbe.storage_backend_id == storage_backend_id)
            .order_by(desc(StorageBackendProbe.observed_at))
            .limit(limit)
        )
    )
    return [StorageBackendProbeSample.model_validate(row) for row in rows]

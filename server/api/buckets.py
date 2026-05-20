import datetime as dt
import uuid

from api.dependencies import AdminUser, UnitOfWorkDep
from application.context import context_from_headers
from application.control_plane import buckets
from application.control_plane.bucket_mutations import (
    create_bucket as create_bucket_use_case,
    delete_bucket as delete_bucket_use_case,
    probe_bucket as probe_bucket_use_case,
    update_bucket as update_bucket_use_case,
)
from application.control_plane.drain_bucket import drain_bucket as drain_bucket_use_case
from enums import StorageKind
from fastapi import APIRouter, Query, Request, Response, status
from infra.db.models import BucketProbe
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, select

router = APIRouter()

"""
Bucket backend management. Admin-only across the board - buckets are
infrastructure, not user data.

The access credentials are encrypted at rest with settings.ENCRYPTION_SECRET.

There is no static "tier" anymore. Placement ranks buckets by their recent
probe latency (see infra.db.stores.placement.hotness_ranked_buckets) and the cron
job rebalances blobs based on access patterns + bucket pressure.
"""


class BucketCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    endpoint: str = Field(min_length=1)
    region: str = Field(min_length=1, max_length=128)
    bucket: str = Field(min_length=1, max_length=255)
    key_id: str = Field(min_length=1)
    secret_access_key: str = Field(min_length=1)
    max_size_bytes: int = Field(gt=0)
    storage_kind: StorageKind = StorageKind.S3


class BucketUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    endpoint: str | None = Field(default=None, min_length=1)
    region: str | None = Field(default=None, min_length=1, max_length=128)
    bucket: str | None = Field(default=None, min_length=1, max_length=255)
    max_size_bytes: int | None = Field(default=None, gt=0)
    key_id: str | None = Field(default=None, min_length=1)
    secret_access_key: str | None = Field(default=None, min_length=1)
    storage_kind: StorageKind | None = None


class BucketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    name: str
    endpoint: str
    region: str
    bucket: str
    key_id: str
    secret_access_key: str
    max_size_bytes: int
    storage_kind: StorageKind
    object_count: int
    current_size_bytes: int
    avg_latency_ms: float | None
    probe_sample_count: int
    reachable: bool


class BucketProbeRead(BucketRead):
    pass


class BucketProbeSample(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: uuid.UUID
    observed_at: dt.datetime
    success: bool
    put_ms: int | None
    head_ms: int | None
    get_ms: int | None
    delete_ms: int | None


@router.get("/")
async def list_buckets(request: Request, uow: UnitOfWorkDep) -> list[BucketRead]:
    """
    GET /buckets -> list all configured buckets.
    Includes blob-derived usage and the rolling-average probe latency.
    """
    return buckets.list_bucket_reads(uow)


@router.post("/")
async def create_bucket(
    request: Request,
    payload: BucketCreate,
    uow: UnitOfWorkDep,
    current_user: AdminUser,
) -> BucketRead:
    """
    POST /buckets -> register a new bucket backend.
    Body: { name, endpoint, region, bucket, key_id, secret_access_key, max_size_bytes }
    """
    bucket = create_bucket_use_case(
        uow,
        payload.model_dump(),
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )
    return buckets.get_bucket_read(uow, bucket.id)


@router.get("/{bucket_id}")
async def get_bucket(
    bucket_id: uuid.UUID, request: Request, uow: UnitOfWorkDep
) -> BucketRead:
    """GET /buckets/{id} -> single bucket with usage and rolling-average latency."""
    return buckets.get_bucket_read(uow, bucket_id)


@router.patch("/{bucket_id}")
async def update_bucket(
    bucket_id: uuid.UUID,
    request: Request,
    payload: BucketUpdate,
    uow: UnitOfWorkDep,
    current_user: AdminUser,
) -> BucketRead:
    """PATCH /buckets/{id} -> update mutable fields."""
    update_bucket_use_case(
        uow,
        bucket_id,
        payload.model_dump(exclude_unset=True),
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )
    return buckets.get_bucket_read(uow, bucket_id)


@router.delete("/{bucket_id}")
async def delete_bucket(
    bucket_id: uuid.UUID,
    request: Request,
    uow: UnitOfWorkDep,
    current_user: AdminUser,
) -> Response:
    """
    DELETE /buckets/{id} -> remove a bucket backend.
    Refuses if any Blobs still reference it; migrate them out first.
    Returns 409 with blob count if the constraint blocks.
    """
    delete_bucket_use_case(
        uow,
        bucket_id,
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{bucket_id}/probe")
async def probe_bucket(
    bucket_id: uuid.UUID,
    request: Request,
    uow: UnitOfWorkDep,
    current_user: AdminUser,
) -> BucketProbeRead:
    """
    POST /buckets/{id}/probe -> trigger sequential PUT/HEAD/GET/DELETE probes.
    Writes a fresh row into bucket_probes; the placement ranking averages the
    most recent N successful probes.
    """
    probe_bucket_use_case(uow, bucket_id)
    return BucketProbeRead(**buckets.get_bucket_read(uow, bucket_id))


class DrainBucketResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    moved: int
    skipped: int
    failed: int
    scanned: int


@router.post("/{bucket_id}/drain")
async def drain_bucket(
    bucket_id: uuid.UUID,
    uow: UnitOfWorkDep,
    current_user: AdminUser,
) -> DrainBucketResponse:
    """POST /buckets/{id}/drain -> migrate all blobs to colder buckets with capacity."""
    del current_user
    result = drain_bucket_use_case(uow, bucket_id=bucket_id)
    return DrainBucketResponse(
        moved=result["moved"],
        skipped=result["skipped"],
        failed=result["failed"],
        scanned=result["scanned"],
    )


@router.get("/{bucket_id}/probes")
async def list_bucket_probes(
    bucket_id: uuid.UUID,
    request: Request,
    uow: UnitOfWorkDep,
    current_user: AdminUser,
    limit: int = Query(default=20, ge=1, le=200),
) -> list[BucketProbeSample]:
    """GET /buckets/{id}/probes -> recent probe samples (newest first)."""
    buckets.get_bucket(uow, bucket_id)
    rows = list(
        uow.session.scalars(
            select(BucketProbe)
            .where(BucketProbe.bucket_id == bucket_id)
            .order_by(desc(BucketProbe.observed_at))
            .limit(limit)
        )
    )
    return [BucketProbeSample.model_validate(row) for row in rows]

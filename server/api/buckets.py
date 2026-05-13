import datetime as dt
import uuid

from database import DbSession
from fastapi import APIRouter, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, select
from services import buckets as bucket_service
from services.event_context import context_from_headers
from models import BucketProbe

from api.dependencies import AdminUser

router = APIRouter()

"""
Bucket backend management. Admin-only across the board - buckets are
infrastructure, not user data.

The access credentials are encrypted at rest with settings.ENCRYPTION_SECRET.

There is no static "tier" anymore. Placement ranks buckets by their recent
probe latency (see services.placement.hotness_ranked_buckets) and the cron
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


class BucketUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    endpoint: str | None = Field(default=None, min_length=1)
    region: str | None = Field(default=None, min_length=1, max_length=128)
    bucket: str | None = Field(default=None, min_length=1, max_length=255)
    max_size_bytes: int | None = Field(default=None, gt=0)
    key_id: str | None = Field(default=None, min_length=1)
    secret_access_key: str | None = Field(default=None, min_length=1)


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
async def list_buckets(request: Request, db: DbSession) -> list[BucketRead]:
    """
    GET /buckets -> list all configured buckets.
    Includes blob-derived usage and the rolling-average probe latency.
    """
    return bucket_service.list_bucket_reads(db)


@router.post("/")
async def create_bucket(
    request: Request, payload: BucketCreate, db: DbSession, current_user: AdminUser
) -> BucketRead:
    """
    POST /buckets -> register a new bucket backend.
    Body: { name, endpoint, region, bucket, key_id, secret_access_key, max_size_bytes }
    """
    return bucket_service.create_bucket_read(
        db,
        payload.model_dump(),
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )


@router.get("/{bucket_id}")
async def get_bucket(
    bucket_id: uuid.UUID, request: Request, db: DbSession
) -> BucketRead:
    """GET /buckets/{id} -> single bucket with usage and rolling-average latency."""
    return bucket_service.get_bucket_read(db, bucket_id)


@router.patch("/{bucket_id}")
async def update_bucket(
    bucket_id: uuid.UUID,
    request: Request,
    payload: BucketUpdate,
    db: DbSession,
    current_user: AdminUser,
) -> BucketRead:
    """PATCH /buckets/{id} -> update mutable fields."""
    return bucket_service.update_bucket_read(
        db,
        bucket_id,
        payload.model_dump(exclude_unset=True),
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )


@router.delete("/{bucket_id}")
async def delete_bucket(
    bucket_id: uuid.UUID, request: Request, db: DbSession, current_user: AdminUser
) -> Response:
    """
    DELETE /buckets/{id} -> remove a bucket backend.
    Refuses if any Blobs still reference it; migrate them out first.
    Returns 409 with blob count if the constraint blocks.
    """
    bucket_service.delete_bucket(
        db,
        bucket_id,
        event_context=context_from_headers(
            request.headers,
            actor_id=current_user.id,
        ),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{bucket_id}/probe")
async def probe_bucket(
    bucket_id: uuid.UUID, request: Request, db: DbSession, current_user: AdminUser
) -> BucketProbeRead:
    """
    POST /buckets/{id}/probe -> trigger sequential PUT/HEAD/GET/DELETE probes.
    Writes a fresh row into bucket_probes; the placement ranking averages the
    most recent N successful probes.
    """
    bucket_service.probe_bucket(db, bucket_id)
    return BucketProbeRead(**bucket_service.get_bucket_read(db, bucket_id))


@router.get("/{bucket_id}/probes")
async def list_bucket_probes(
    bucket_id: uuid.UUID,
    request: Request,
    db: DbSession,
    current_user: AdminUser,
    limit: int = Query(default=20, ge=1, le=200),
) -> list[BucketProbeSample]:
    """GET /buckets/{id}/probes -> recent probe samples (newest first)."""
    bucket_service.get_bucket(db, bucket_id)
    rows = list(
        db.scalars(
            select(BucketProbe)
            .where(BucketProbe.bucket_id == bucket_id)
            .order_by(desc(BucketProbe.observed_at))
            .limit(limit)
        )
    )
    return [BucketProbeSample.model_validate(row) for row in rows]

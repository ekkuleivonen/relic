import uuid

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies import AdminUser
from database import DbSession
from schema_plan import BucketTier
from services import buckets as bucket_service
from services.event_context import context_from_headers

router = APIRouter()

"""
Bucket backend management. Admin-only across the board - buckets are
infrastructure, not user data.

The access credentials are encrypted at rest with settings.ENCRYPTION_SECRET.
"""


class BucketCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    endpoint: str = Field(min_length=1)
    region: str = Field(min_length=1, max_length=128)
    bucket: str = Field(min_length=1, max_length=255)
    key_id: str = Field(min_length=1)
    secret_access_key: str = Field(min_length=1)
    tier: BucketTier
    max_size_bytes: int = Field(gt=0)


class BucketUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    endpoint: str | None = Field(default=None, min_length=1)
    region: str | None = Field(default=None, min_length=1, max_length=128)
    bucket: str | None = Field(default=None, min_length=1, max_length=255)
    tier: BucketTier | None = None
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
    tier: BucketTier
    max_size_bytes: int
    object_count: int
    current_size_bytes: int
    probe_latency_put_ms: int | None
    probe_latency_head_ms: int | None
    probe_latency_get_ms: int | None
    probe_latency_delete_ms: int | None


class BucketProbeRead(BucketRead):
    reachable: bool


@router.get("/")
async def list_buckets(request: Request, db: DbSession) -> list[BucketRead]:
    """
    GET /buckets -> list all configured buckets.
    Includes blob-derived usage and probe latency snapshots.
    """
    return bucket_service.list_bucket_reads(db)


@router.post("/")
async def create_bucket(
    request: Request, payload: BucketCreate, db: DbSession, current_user: AdminUser
) -> BucketRead:
    """
    POST /buckets -> register a new bucket backend.
    Body: { name, endpoint, region, bucket, key_id, secret_access_key, tier, max_size_bytes }
    """
    return bucket_service.create_bucket_read(
        db,
        payload.model_dump(),
        event_context=context_from_headers(
            request.headers,
            actor_user_id=current_user.id,
        ),
    )


@router.get("/{bucket_id}")
async def get_bucket(bucket_id: uuid.UUID, request: Request, db: DbSession) -> BucketRead:
    """
    GET /buckets/{id} -> single bucket with blob-derived usage and probe latencies.
    """
    return bucket_service.get_bucket_read(db, bucket_id)


@router.patch("/{bucket_id}")
async def update_bucket(
    bucket_id: uuid.UUID,
    request: Request,
    payload: BucketUpdate,
    db: DbSession,
    current_user: AdminUser,
) -> BucketRead:
    """
    PATCH /buckets/{id} -> update mutable fields.
    Body: { name?, endpoint?, region?, bucket?, tier?, max_size_bytes?, key_id?, secret_access_key? }
    """
    return bucket_service.update_bucket_read(
        db,
        bucket_id,
        payload.model_dump(exclude_unset=True),
        event_context=context_from_headers(
            request.headers,
            actor_user_id=current_user.id,
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
            actor_user_id=current_user.id,
        ),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{bucket_id}/probe")
async def probe_bucket(
    bucket_id: uuid.UUID, request: Request, db: DbSession, current_user: AdminUser
) -> BucketProbeRead:
    """
    POST /buckets/{id}/probe -> trigger sequential PUT/HEAD/GET/DELETE probes.
    Returns the fresh snapshot. Useful after capacity changes or for debugging.
    Normally a cron job does this; this is the manual override.
    """
    result = bucket_service.probe_bucket(
        db,
        bucket_id,
    )
    bucket_data = bucket_service.get_bucket_read(db, result.bucket.id)
    return BucketProbeRead(**bucket_data, reachable=result.reachable)


@router.post("/{bucket_id}/drain")
async def drain_bucket(
    bucket_id: uuid.UUID, request: Request, db: DbSession, current_user: AdminUser
) -> Response:
    """
    POST /buckets/{id}/drain -> mark for draining; migrate all blobs to
    other buckets of the same or compatible tier in the background.
    Status is queryable via GET /buckets/{id}.
    Used when retiring a bucket backend.
    """
    bucket_service.drain_bucket(
        db,
        bucket_id,
    )
    return Response(status_code=status.HTTP_202_ACCEPTED)

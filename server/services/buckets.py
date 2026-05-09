import time
import uuid
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from managers.exceptions import BadRequestError, ConflictError, ResourceNotFound
from models import Blob, Bucket


@dataclass(frozen=True)
class BucketProbeResult:
    bucket: Bucket
    reachable: bool


def list_buckets(db: Session) -> list[Bucket]:
    return list(db.scalars(select(Bucket).order_by(Bucket.name)))


def get_bucket(db: Session, bucket_id: uuid.UUID) -> Bucket:
    bucket = db.get(Bucket, bucket_id)
    if not bucket:
        raise ResourceNotFound("Bucket not found")
    return bucket


def create_bucket(db: Session, values: dict[str, Any]) -> Bucket:
    ensure_bucket_name_available(db, values["name"])
    bucket = Bucket(**values)
    db.add(bucket)
    db.commit()
    db.refresh(bucket)
    return bucket


def update_bucket(db: Session, bucket_id: uuid.UUID, values: dict[str, Any]) -> Bucket:
    bucket = get_bucket(db, bucket_id)
    if "name" in values:
        ensure_bucket_name_available(db, values["name"], excluding_id=bucket.id)

    for key, value in values.items():
        setattr(bucket, key, value)

    db.commit()
    db.refresh(bucket)
    return bucket


def delete_bucket(db: Session, bucket_id: uuid.UUID) -> None:
    bucket = get_bucket(db, bucket_id)
    blob_count = db.scalar(
        select(func.count()).select_from(Blob).where(Blob.bucket_id == bucket.id)
    )
    if blob_count:
        raise ConflictError(
            "Bucket still has blobs",
            detail={"message": "Bucket still has blobs", "blob_count": blob_count},
        )

    db.delete(bucket)
    db.commit()


def probe_bucket(db: Session, bucket_id: uuid.UUID) -> BucketProbeResult:
    bucket = get_bucket(db, bucket_id)
    probe_key = f"__relic_probe__/{uuid.uuid4()}"
    probe_body = b"relic-probe"
    reachable = True

    try:
        client = boto3.client(
            "s3",
            endpoint_url=bucket.endpoint,
            region_name=bucket.region,
            aws_access_key_id=bucket.key_id,
            aws_secret_access_key=bucket.secret_access_key,
        )
        bucket.probe_latency_put_ms = timed_ms(
            lambda: client.put_object(Bucket=bucket.bucket, Key=probe_key, Body=probe_body)
        )
        bucket.probe_latency_head_ms = timed_ms(
            lambda: client.head_object(Bucket=bucket.bucket, Key=probe_key)
        )
        bucket.probe_latency_get_ms = timed_ms(
            lambda: client.get_object(Bucket=bucket.bucket, Key=probe_key)["Body"].read()
        )
        bucket.probe_latency_delete_ms = timed_ms(
            lambda: client.delete_object(Bucket=bucket.bucket, Key=probe_key)
        )
    except (BotoCoreError, ClientError):
        reachable = False

    db.commit()
    db.refresh(bucket)
    return BucketProbeResult(bucket=bucket, reachable=reachable)


def timed_ms(operation) -> int:
    started = time.perf_counter()
    operation()
    return max(1, round((time.perf_counter() - started) * 1000))


def drain_bucket(db: Session, bucket_id: uuid.UUID) -> None:
    get_bucket(db, bucket_id)
    raise BadRequestError("Bucket drain requires the background migration worker")


def ensure_bucket_name_available(
    db: Session, name: str, *, excluding_id: uuid.UUID | None = None
) -> None:
    existing = db.scalar(select(Bucket).where(Bucket.name == name))
    if existing and existing.id != excluding_id:
        raise ConflictError("A bucket with this name already exists")

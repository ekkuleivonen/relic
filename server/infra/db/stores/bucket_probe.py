"""Sequential PUT/HEAD/GET/DELETE probe against a bucket backend."""

import uuid

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from infra.db.models import BucketProbe
from infra.db.stores.bucket_reads import BucketProbeResult, timed_ms
from ports.uow import UnitOfWork
from utils.logging import get_logger

log = get_logger(__name__)


def probe_bucket(uow: UnitOfWork, bucket_id: uuid.UUID) -> BucketProbeResult:
    bucket = uow.buckets.get(bucket_id)
    probe_key = f"__relic_probe__/{uuid.uuid4()}"
    probe_body = b"relic-probe"
    put_ms: int | None = None
    head_ms: int | None = None
    get_ms: int | None = None
    delete_ms: int | None = None
    reachable = True

    try:
        client = boto3.client(
            "s3",
            endpoint_url=bucket.endpoint,
            region_name=bucket.region,
            aws_access_key_id=bucket.key_id,
            aws_secret_access_key=bucket.secret_access_key,
        )
        put_ms = timed_ms(
            lambda: client.put_object(
                Bucket=bucket.bucket, Key=probe_key, Body=probe_body
            )
        )
        head_ms = timed_ms(
            lambda: client.head_object(Bucket=bucket.bucket, Key=probe_key)
        )
        get_ms = timed_ms(
            lambda: client.get_object(Bucket=bucket.bucket, Key=probe_key)["Body"].read()
        )
        delete_ms = timed_ms(
            lambda: client.delete_object(Bucket=bucket.bucket, Key=probe_key)
        )
    except (BotoCoreError, ClientError, OSError, ValueError) as exc:
        reachable = False
        log.warning(
            "bucket_probe_failed",
            bucket_id=str(bucket.id),
            error=str(exc),
        )

    probe = BucketProbe(
        bucket_id=bucket.id,
        success=reachable,
        put_ms=put_ms,
        head_ms=head_ms,
        get_ms=get_ms,
        delete_ms=delete_ms,
    )
    uow.buckets.add_probe(probe)
    uow.buckets.refresh(bucket, probe)
    return BucketProbeResult(bucket=bucket, probe=probe, reachable=reachable)

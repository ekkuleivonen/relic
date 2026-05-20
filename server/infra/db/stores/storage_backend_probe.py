"""Sequential PUT/HEAD/GET/DELETE probe against a bucket backend."""

import uuid
from io import BytesIO

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from enums import StorageBackendKind
from infra.db.models import StorageBackendProbe
from infra.db.stores.storage_backend_reads import StorageBackendProbeResult, timed_ms
from infra.object_storage.filesystem import FilesystemObjectStorage
from ports.uow import UnitOfWork
from utils.logging import get_logger

log = get_logger(__name__)


def probe_storage_backend(uow: UnitOfWork, storage_backend_id: uuid.UUID) -> StorageBackendProbeResult:
    bucket = uow.storage_backends.get(storage_backend_id)
    probe_key = f"__relic_probe__/{uuid.uuid4()}"
    probe_body = b"relic-probe"
    put_ms: int | None = None
    head_ms: int | None = None
    get_ms: int | None = None
    delete_ms: int | None = None
    reachable = True

    try:
        if bucket.kind == StorageBackendKind.FILESYSTEM:
            storage = FilesystemObjectStorage(bucket.endpoint)
            put_ms = timed_ms(
                lambda: storage.put(
                    namespace=bucket.namespace,
                    key=probe_key,
                    body=BytesIO(probe_body),
                    size=len(probe_body),
                )
            )
            head_ms = timed_ms(
                lambda: storage.head(namespace=bucket.namespace, key=probe_key)
            )
            get_ms = timed_ms(
                lambda: storage.get(namespace=bucket.namespace, key=probe_key)
            )
            delete_ms = timed_ms(
                lambda: storage.delete(namespace=bucket.namespace, key=probe_key)
            )
        else:
            client = boto3.client(
                "s3",
                endpoint_url=bucket.endpoint,
                region_name=bucket.region,
                aws_access_key_id=bucket.key_id,
                aws_secret_access_key=bucket.secret_access_key,
            )
            put_ms = timed_ms(
                lambda: client.put_object(
                    Bucket=bucket.namespace, Key=probe_key, Body=probe_body
                )
            )
            head_ms = timed_ms(
                lambda: client.head_object(Bucket=bucket.namespace, Key=probe_key)
            )
            get_ms = timed_ms(
                lambda: client.get_object(Bucket=bucket.namespace, Key=probe_key)[
                    "Body"
                ].read()
            )
            delete_ms = timed_ms(
                lambda: client.delete_object(Bucket=bucket.namespace, Key=probe_key)
            )
    except (BotoCoreError, ClientError, OSError, ValueError) as exc:
        reachable = False
        log.warning(
            "storage_backend_probe_failed",
            storage_backend_id=str(bucket.id),
            error=str(exc),
        )

    probe = StorageBackendProbe(
        storage_backend_id=bucket.id,
        success=reachable,
        put_ms=put_ms,
        head_ms=head_ms,
        get_ms=get_ms,
        delete_ms=delete_ms,
    )
    uow.storage_backends.add_probe(probe)
    uow.storage_backends.refresh(bucket, probe)
    return StorageBackendProbeResult(storage_backend=bucket, probe=probe, reachable=reachable)

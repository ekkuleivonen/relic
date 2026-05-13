import asyncio
import uuid

from arq.cron import cron

from database import get_sessionmaker
from services import audit_events as audit_event_service
from services import file_events as file_event_service
from services import maintenance_events as maintenance_event_service
from services import storage_maintenance
from infra.arq import arq_redis_settings
from utils.logging import get_logger

import settings as S

log = get_logger(__name__)


async def purge_dereferenced_blobs_worker(ctx) -> None:
    del ctx

    def run() -> None:
        batch_id = uuid.uuid4()
        sm = get_sessionmaker()
        with sm() as db:
            storage_maintenance.purge_dereferenced_blobs_batch(
                db,
                batch=S.STORAGE_MAINTENANCE_PURGE_BATCH,
                batch_id=batch_id,
            )

    await asyncio.to_thread(run)


async def refresh_all_bucket_probes_worker(ctx) -> None:
    del ctx

    def run() -> None:
        batch_id = uuid.uuid4()
        sm = get_sessionmaker()
        with sm() as db:
            storage_maintenance.probe_all_buckets(db, batch_id=batch_id)

    await asyncio.to_thread(run)


async def rebalance_blob_storage_worker(ctx) -> None:
    del ctx

    def run() -> None:
        batch_id = uuid.uuid4()
        sm = get_sessionmaker()
        with sm() as db:
            storage_maintenance.rebalance_blob_storage_batch(
                db,
                migrate_limit=S.STORAGE_MAINTENANCE_MIGRATE_BATCH,
                pressure_ratio=S.STORAGE_MAINTENANCE_BUCKET_PRESSURE_RATIO,
                batch_id=batch_id,
            )

    await asyncio.to_thread(run)


async def trim_old_audit_events_worker(ctx) -> None:
    del ctx

    def run() -> None:
        batch_id = uuid.uuid4()
        sm = get_sessionmaker()
        with sm() as db:
            deleted_rows = audit_event_service.trim_audit_events_older_than(
                db,
                retention_days=S.EVENT_RETENTION_DAYS,
            )
            maintenance_event_service.create_maintenance_event(
                db,
                job="trim_audit_events",
                action="audit.trimmed",
                status="succeeded",
                batch_id=batch_id,
                metadata={
                    "retention_days": S.EVENT_RETENTION_DAYS,
                    "deleted_rows": deleted_rows,
                },
            )
            db.commit()
        log.info(
            "audit_event_retention_trimmed",
            retention_days=S.EVENT_RETENTION_DAYS,
            deleted_rows=deleted_rows,
        )

    await asyncio.to_thread(run)


async def trim_old_file_events_worker(ctx) -> None:
    del ctx

    def run() -> None:
        batch_id = uuid.uuid4()
        sm = get_sessionmaker()
        with sm() as db:
            deleted_rows = file_event_service.trim_file_events_older_than(
                db,
                retention_days=S.EVENT_RETENTION_DAYS,
            )
            maintenance_event_service.create_maintenance_event(
                db,
                job="trim_file_events",
                action="file_event.trimmed",
                status="succeeded",
                batch_id=batch_id,
                metadata={
                    "retention_days": S.EVENT_RETENTION_DAYS,
                    "deleted_rows": deleted_rows,
                },
            )
            db.commit()
        log.info(
            "file_event_retention_trimmed",
            retention_days=S.EVENT_RETENTION_DAYS,
            deleted_rows=deleted_rows,
        )

    await asyncio.to_thread(run)


async def trim_old_maintenance_events_worker(ctx) -> None:
    del ctx

    def run() -> None:
        batch_id = uuid.uuid4()
        sm = get_sessionmaker()
        with sm() as db:
            deleted_rows = maintenance_event_service.trim_maintenance_events_older_than(
                db,
                retention_days=S.EVENT_RETENTION_DAYS,
            )
            maintenance_event_service.create_maintenance_event(
                db,
                job="trim_maintenance_events",
                action="maintenance_event.trimmed",
                status="succeeded",
                batch_id=batch_id,
                metadata={
                    "retention_days": S.EVENT_RETENTION_DAYS,
                    "deleted_rows": deleted_rows,
                },
            )
            db.commit()
        log.info(
            "maintenance_event_retention_trimmed",
            retention_days=S.EVENT_RETENTION_DAYS,
            deleted_rows=deleted_rows,
        )

    await asyncio.to_thread(run)


async def storage_maintenance_tick(ctx) -> None:
    redis = ctx["redis"]
    await redis.enqueue_job("purge_dereferenced_blobs_worker")
    await redis.enqueue_job("refresh_all_bucket_probes_worker")
    await redis.enqueue_job("rebalance_blob_storage_worker")
    await redis.enqueue_job("trim_old_audit_events_worker")
    await redis.enqueue_job("trim_old_file_events_worker")
    await redis.enqueue_job("trim_old_maintenance_events_worker")
    log.info(
        "storage_maintenance_tick_enqueued",
        queue=S.MAINTENANCE_QUEUE_NAME,
    )


class WorkerSettings:
    functions = [
        purge_dereferenced_blobs_worker,
        refresh_all_bucket_probes_worker,
        rebalance_blob_storage_worker,
        trim_old_audit_events_worker,
        trim_old_file_events_worker,
        trim_old_maintenance_events_worker,
    ]
    cron_jobs = [
        cron(
            storage_maintenance_tick,
            minute={*range(60)},
            second=0,
        ),
    ]
    redis_settings = arq_redis_settings()
    queue_name = S.MAINTENANCE_QUEUE_NAME

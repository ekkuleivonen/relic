import asyncio

from arq.cron import cron

from database import get_sessionmaker
from services import audit_events as audit_event_service
from services import file_events as file_event_service
from services import storage_maintenance
from services.processor_queue import redis_settings
from utils.logging import get_logger

import settings as S

log = get_logger(__name__)


async def purge_dereferenced_blobs_worker(ctx) -> None:
    del ctx

    def run() -> None:
        sm = get_sessionmaker()
        with sm() as db:
            storage_maintenance.purge_dereferenced_blobs_batch(
                db,
                batch=S.STORAGE_MAINTENANCE_PURGE_BATCH,
            )

    await asyncio.to_thread(run)


async def refresh_all_bucket_probes_worker(ctx) -> None:
    del ctx

    def run() -> None:
        sm = get_sessionmaker()
        with sm() as db:
            storage_maintenance.probe_all_buckets(db)

    await asyncio.to_thread(run)


async def rebalance_blob_storage_worker(ctx) -> None:
    del ctx

    def run() -> None:
        sm = get_sessionmaker()
        with sm() as db:
            storage_maintenance.rebalance_blob_storage_batch(
                db,
                migrate_limit=S.STORAGE_MAINTENANCE_MIGRATE_BATCH,
                pressure_ratio=S.STORAGE_MAINTENANCE_BUCKET_PRESSURE_RATIO,
            )

    await asyncio.to_thread(run)


async def trim_old_audit_events_worker(ctx) -> None:
    del ctx

    def run() -> None:
        sm = get_sessionmaker()
        with sm() as db:
            deleted_rows = audit_event_service.trim_audit_events_older_than(
                db,
                retention_days=S.EVENT_RETENTION_DAYS,
            )
        log.info(
            "audit_event_retention_trimmed",
            retention_days=S.EVENT_RETENTION_DAYS,
            deleted_rows=deleted_rows,
        )

    await asyncio.to_thread(run)


async def trim_old_file_events_worker(ctx) -> None:
    del ctx

    def run() -> None:
        sm = get_sessionmaker()
        with sm() as db:
            deleted_rows = file_event_service.trim_file_events_older_than(
                db,
                retention_days=S.EVENT_RETENTION_DAYS,
            )
        log.info(
            "file_event_retention_trimmed",
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
    ]
    cron_jobs = [
        cron(
            storage_maintenance_tick,
            minute={*range(60)},
            second=0,
        ),
    ]
    redis_settings = redis_settings()
    queue_name = S.MAINTENANCE_QUEUE_NAME

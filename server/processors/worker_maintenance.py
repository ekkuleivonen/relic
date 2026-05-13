import asyncio
import datetime as dt
import uuid

from arq.cron import cron

from database import get_sessionmaker
from services import audit_events as audit_event_service
from services import file_events as file_event_service
from services import maintenance_events as maintenance_event_service
from services import s3_multipart
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


async def trim_old_bucket_probes_worker(ctx) -> None:
    del ctx

    def run() -> None:
        batch_id = uuid.uuid4()
        sm = get_sessionmaker()
        with sm() as db:
            storage_maintenance.trim_old_bucket_probes_batch(
                db,
                retention_days=S.PROBES_RETENTION_DAYS,
                batch_id=batch_id,
            )

    await asyncio.to_thread(run)


async def demote_pressured_buckets_worker(ctx) -> None:
    del ctx

    def run() -> None:
        batch_id = uuid.uuid4()
        sm = get_sessionmaker()
        with sm() as db:
            storage_maintenance.demote_pressured_buckets_batch(
                db,
                demote_limit=S.STORAGE_DEMOTE_BATCH,
                pressure_ratio=S.STORAGE_DEMOTION_PRESSURE_RATIO,
                headroom_ratio=S.STORAGE_PROMOTION_HEADROOM_RATIO,
                min_residency_hours=S.STORAGE_MIGRATION_MIN_RESIDENCY_HOURS,
                batch_id=batch_id,
            )

    await asyncio.to_thread(run)


async def promote_recently_accessed_worker(ctx) -> None:
    del ctx

    def run() -> None:
        batch_id = uuid.uuid4()
        sm = get_sessionmaker()
        with sm() as db:
            storage_maintenance.promote_recently_accessed_batch(
                db,
                promote_limit=S.STORAGE_PROMOTE_BATCH,
                headroom_ratio=S.STORAGE_PROMOTION_HEADROOM_RATIO,
                recency_days=S.STORAGE_PROMOTION_RECENCY_DAYS,
                min_residency_hours=S.STORAGE_MIGRATION_MIN_RESIDENCY_HOURS,
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


async def abort_incomplete_multipart_uploads_worker(ctx) -> None:
    del ctx

    def run() -> None:
        batch_id = uuid.uuid4()
        cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(
            hours=S.S3_MULTIPART_ABORT_INCOMPLETE_AFTER_HOURS
        )
        sm = get_sessionmaker()
        with sm() as db:
            deleted_rows = s3_multipart.abort_incomplete_uploads_older_than(db, cutoff)
            maintenance_event_service.create_maintenance_event(
                db,
                job="abort_incomplete_multipart_uploads",
                action="multipart_upload.aborted",
                status="succeeded",
                batch_id=batch_id,
                metadata={
                    "abort_after_hours": S.S3_MULTIPART_ABORT_INCOMPLETE_AFTER_HOURS,
                    "deleted_rows": deleted_rows,
                },
            )
            db.commit()
        log.info(
            "multipart_upload_retention_aborted",
            abort_after_hours=S.S3_MULTIPART_ABORT_INCOMPLETE_AFTER_HOURS,
            deleted_rows=deleted_rows,
        )

    await asyncio.to_thread(run)


async def storage_maintenance_tick(ctx) -> None:
    redis = ctx["redis"]
    await redis.enqueue_job("purge_dereferenced_blobs_worker")
    await redis.enqueue_job("refresh_all_bucket_probes_worker")
    await redis.enqueue_job("demote_pressured_buckets_worker")
    await redis.enqueue_job("promote_recently_accessed_worker")
    await redis.enqueue_job("trim_old_bucket_probes_worker")
    await redis.enqueue_job("trim_old_audit_events_worker")
    await redis.enqueue_job("trim_old_file_events_worker")
    await redis.enqueue_job("trim_old_maintenance_events_worker")
    await redis.enqueue_job("abort_incomplete_multipart_uploads_worker")
    log.info(
        "storage_maintenance_tick_enqueued",
        queue=S.MAINTENANCE_QUEUE_NAME,
    )


class WorkerSettings:
    functions = [
        purge_dereferenced_blobs_worker,
        refresh_all_bucket_probes_worker,
        trim_old_bucket_probes_worker,
        demote_pressured_buckets_worker,
        promote_recently_accessed_worker,
        trim_old_audit_events_worker,
        trim_old_file_events_worker,
        trim_old_maintenance_events_worker,
        abort_incomplete_multipart_uploads_worker,
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

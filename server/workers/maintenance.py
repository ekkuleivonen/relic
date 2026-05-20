import asyncio
import datetime as dt
import uuid

from arq.cron import cron

from application.maintenance import retention as retention_maintenance
from infra import metrics
from infra.maintenance import storage as storage_maintenance
from infra.worker_heartbeats import touch_maintenance_heartbeat
from application.uow_runner import run_with_uow
from infra.arq import arq_redis_settings
from infra.db.engine import get_sessionmaker
from utils.logging import get_logger

import settings as S

log = get_logger(__name__)


async def purge_dereferenced_blobs_worker(ctx) -> None:
    del ctx

    def run() -> None:
        batch_id = uuid.uuid4()
        sm = get_sessionmaker()
        with sm() as db:
            run_with_uow(
                db,
                lambda uow: storage_maintenance.purge_dereferenced_blobs_batch(
                    uow,
                    batch=S.STORAGE_MAINTENANCE_PURGE_BATCH,
                    batch_id=batch_id,
                ),
            )

    await _run_maintenance_job("purge_dereferenced_blobs", run)


async def refresh_all_storage_backend_probes_worker(ctx) -> None:
    del ctx

    def run() -> None:
        batch_id = uuid.uuid4()
        sm = get_sessionmaker()
        with sm() as db:
            run_with_uow(
                db,
                lambda uow: storage_maintenance.probe_all_storage_backends(
                    uow, batch_id=batch_id
                ),
            )

    await _run_maintenance_job("refresh_all_storage_backend_probes", run)


async def trim_old_storage_backend_probes_worker(ctx) -> None:
    del ctx

    def run() -> None:
        batch_id = uuid.uuid4()
        sm = get_sessionmaker()
        with sm() as db:
            run_with_uow(
                db,
                lambda uow: storage_maintenance.trim_old_storage_backend_probes_batch(
                    uow,
                    retention_days=S.PROBES_RETENTION_DAYS,
                    batch_id=batch_id,
                ),
            )

    await _run_maintenance_job("trim_old_storage_backend_probes", run)


async def demote_pressured_buckets_worker(ctx) -> None:
    del ctx

    def run() -> None:
        batch_id = uuid.uuid4()
        sm = get_sessionmaker()
        with sm() as db:
            run_with_uow(
                db,
                lambda uow: storage_maintenance.demote_pressured_storage_backends_batch(
                    uow,
                    demote_limit=S.STORAGE_DEMOTE_BATCH,
                    pressure_ratio=S.STORAGE_DEMOTION_PRESSURE_RATIO,
                    headroom_ratio=S.STORAGE_PROMOTION_HEADROOM_RATIO,
                    min_residency_hours=S.STORAGE_MIGRATION_MIN_RESIDENCY_HOURS,
                    batch_id=batch_id,
                ),
            )

    await _run_maintenance_job("demote_pressured_buckets", run)


async def promote_recently_accessed_worker(ctx) -> None:
    del ctx

    def run() -> None:
        batch_id = uuid.uuid4()
        sm = get_sessionmaker()
        with sm() as db:
            run_with_uow(
                db,
                lambda uow: storage_maintenance.promote_recently_accessed_batch(
                    uow,
                    promote_limit=S.STORAGE_PROMOTE_BATCH,
                    headroom_ratio=S.STORAGE_PROMOTION_HEADROOM_RATIO,
                    recency_days=S.STORAGE_PROMOTION_RECENCY_DAYS,
                    min_residency_hours=S.STORAGE_MIGRATION_MIN_RESIDENCY_HOURS,
                    batch_id=batch_id,
                ),
            )

    await _run_maintenance_job("promote_recently_accessed", run)


async def trim_old_audit_events_worker(ctx) -> None:
    del ctx

    def run() -> None:
        batch_id = uuid.uuid4()
        sm = get_sessionmaker()
        with sm() as db:
            audit_deleted = run_with_uow(
                db,
                lambda uow: retention_maintenance.trim_old_audit_events(
                    uow,
                    retention_days=S.EVENT_RETENTION_DAYS,
                    batch_id=batch_id,
                ),
            )
            file_deleted = run_with_uow(
                db,
                lambda uow: retention_maintenance.trim_old_file_events(
                    uow,
                    retention_days=S.EVENT_RETENTION_DAYS,
                    batch_id=batch_id,
                ),
            )
        log.info(
            "event_retention_trimmed",
            retention_days=S.EVENT_RETENTION_DAYS,
            audit_deleted_rows=audit_deleted,
            file_deleted_rows=file_deleted,
        )

    await _run_maintenance_job("trim_old_audit_events", run)


async def abort_incomplete_multipart_uploads_worker(ctx) -> None:
    del ctx

    def run() -> None:
        batch_id = uuid.uuid4()
        cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(
            hours=S.S3_MULTIPART_ABORT_INCOMPLETE_AFTER_HOURS
        )
        sm = get_sessionmaker()
        with sm() as db:
            deleted_rows = run_with_uow(
                db,
                lambda uow: retention_maintenance.abort_incomplete_multipart_uploads(
                    uow,
                    cutoff=cutoff,
                    batch_id=batch_id,
                    abort_after_hours=S.S3_MULTIPART_ABORT_INCOMPLETE_AFTER_HOURS,
                ),
            )
        log.info(
            "multipart_upload_retention_aborted",
            abort_after_hours=S.S3_MULTIPART_ABORT_INCOMPLETE_AFTER_HOURS,
            deleted_rows=deleted_rows,
        )

    await _run_maintenance_job("abort_incomplete_multipart_uploads", run)


async def storage_maintenance_tick(ctx) -> None:
    started_at = metrics.timer_start()
    status = "succeeded"
    redis = ctx["redis"]
    try:
        await redis.enqueue_job("purge_dereferenced_blobs_worker")
        await redis.enqueue_job("refresh_all_storage_backend_probes_worker")
        await redis.enqueue_job("demote_pressured_buckets_worker")
        await redis.enqueue_job("promote_recently_accessed_worker")
        await redis.enqueue_job("trim_old_storage_backend_probes_worker")
        await redis.enqueue_job("trim_old_audit_events_worker")
        await redis.enqueue_job("abort_incomplete_multipart_uploads_worker")
        queue_depth = int(await redis.zcard(S.MAINTENANCE_QUEUE_NAME))
        metrics.set_maintenance_queue_depth(
            queue=S.MAINTENANCE_QUEUE_NAME,
            depth=queue_depth,
        )
        log.info(
            "storage_maintenance_tick_enqueued",
            queue=S.MAINTENANCE_QUEUE_NAME,
        )
        touch_maintenance_heartbeat()
    except Exception:
        status = "failed"
        raise
    finally:
        metrics.observe_maintenance_job(
            job="storage_maintenance_tick",
            status=status,
            started_at=started_at,
        )


async def _run_maintenance_job(job: str, run) -> None:
    started_at = metrics.timer_start()
    status = "succeeded"
    try:
        await asyncio.to_thread(run)
    except Exception:
        status = "failed"
        raise
    finally:
        touch_maintenance_heartbeat()
        metrics.observe_maintenance_job(job=job, status=status, started_at=started_at)


class WorkerSettings:
    functions = [
        purge_dereferenced_blobs_worker,
        refresh_all_storage_backend_probes_worker,
        trim_old_storage_backend_probes_worker,
        demote_pressured_buckets_worker,
        promote_recently_accessed_worker,
        trim_old_audit_events_worker,
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

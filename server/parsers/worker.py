import asyncio
import uuid

from arq.cron import cron

from database import get_sessionmaker
from parsers import base
from services import storage_maintenance
from services.parser_queue import redis_settings
from utils.logging import get_logger

import settings as S

log = get_logger(__name__)


async def parse_file(ctx, file_id: str) -> None:
    del ctx
    with get_sessionmaker()() as db:
        base.parse_file(db, uuid.UUID(file_id))


async def purge_dereferenced_blobs_worker(ctx) -> None:
    del ctx

    def run() -> None:
        sm = get_sessionmaker()
        with sm() as db:
            storage_maintenance.purge_dereferenced_blobs_batch(
                db, batch=S.STORAGE_MAINTENANCE_PURGE_BATCH
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


async def storage_maintenance_tick(ctx) -> None:
    redis = ctx["redis"]
    await redis.enqueue_job("purge_dereferenced_blobs_worker")
    await redis.enqueue_job("refresh_all_bucket_probes_worker")
    await redis.enqueue_job("rebalance_blob_storage_worker")
    log.info(
        "storage_maintenance_tick_enqueued",
        queue=S.PARSER_QUEUE_NAME,
    )


class WorkerSettings:
    functions = [
        parse_file,
        purge_dereferenced_blobs_worker,
        refresh_all_bucket_probes_worker,
        rebalance_blob_storage_worker,
    ]
    cron_jobs = [
        cron(
            storage_maintenance_tick,
            minute={*range(60)},
            second=0,
        ),
    ]
    redis_settings = redis_settings()
    queue_name = S.PARSER_QUEUE_NAME

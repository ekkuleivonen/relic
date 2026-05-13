"""Pull-based dispatcher for warm processors.

Wakes up on ``LISTEN file_event_emitted`` notifications from Postgres (set
by ``services.file_events.create_file_event``) and additionally ticks on a
safety-net timer so missed notifications don't strand events forever.

For each tick we ask ``services.processors.collect_pending_jobs`` for the
oldest events past every enabled processor's cursor and enqueue them via
arq with ``_job_id = "<processor_id>:<event_id>"`` so a duplicate dispatch
is a no-op as long as the previous job is in-flight.
"""

import asyncio
import signal
from contextlib import suppress

import psycopg
from arq import create_pool
from arq.connections import ArqRedis

from database import get_libpq_dsn, get_sessionmaker
from processors.registry import init_builtin_substrates
from services import processors as processor_service
from services.file_events import FILE_EVENT_CHANNEL
from services.processor_queue import redis_settings
from utils.logging import get_logger

import settings as S

log = get_logger(__name__)


async def main() -> None:
    init_builtin_substrates()
    redis = await create_pool(
        redis_settings(), default_queue_name=S.PROCESSING_QUEUE_NAME
    )
    stop = asyncio.Event()
    _install_signal_handlers(stop)

    listener_task = asyncio.create_task(_listen_loop(redis, stop))
    safety_task = asyncio.create_task(_safety_tick(redis, stop))

    log.info(
        "dispatcher_started",
        channel=FILE_EVENT_CHANNEL,
        safety_interval_s=S.DISPATCHER_SAFETY_INTERVAL_SECONDS,
        batch_size=S.DISPATCHER_BATCH_SIZE,
    )
    try:
        await stop.wait()
    finally:
        listener_task.cancel()
        safety_task.cancel()
        for task in (listener_task, safety_task):
            with suppress(asyncio.CancelledError):
                await task
        await redis.aclose()
        log.info("dispatcher_stopped")


def _install_signal_handlers(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)


async def _listen_loop(redis: ArqRedis, stop: asyncio.Event) -> None:
    """Wake up the dispatcher whenever a new file event is committed.

    Uses ``conn.notifies(timeout=...)`` so the loop wakes periodically even when
    the channel is silent — that gives us a cheap way to honour ``stop`` without
    cancelling pending I/O on the libpq socket (which would force a reconnect).
    """
    poll_timeout = 1.0
    while not stop.is_set():
        try:
            async with await psycopg.AsyncConnection.connect(
                get_libpq_dsn(), autocommit=True
            ) as conn:
                await conn.execute(f"LISTEN {FILE_EVENT_CHANNEL}")
                log.info("dispatcher_listen_attached", channel=FILE_EVENT_CHANNEL)
                while not stop.is_set():
                    received = False
                    async for notify in conn.notifies(timeout=poll_timeout):
                        received = True
                        log.debug(
                            "dispatcher_notify",
                            channel=FILE_EVENT_CHANNEL,
                            payload=notify.payload,
                        )
                    if received:
                        await dispatch_pending(redis)
        except Exception as exc:  # noqa: BLE001 - reconnect on any failure
            if stop.is_set():
                return
            log.warning("dispatcher_listen_reconnect", error=str(exc))
            await asyncio.sleep(min(S.DISPATCHER_LISTEN_BACKOFF_SECONDS, 5))


async def _safety_tick(redis: ArqRedis, stop: asyncio.Event) -> None:
    """Periodic backstop in case a NOTIFY is missed (e.g. listener restart)."""
    while not stop.is_set():
        try:
            await dispatch_pending(redis)
        except Exception as exc:  # noqa: BLE001
            log.warning("dispatcher_safety_tick_failed", error=str(exc))
        try:
            await asyncio.wait_for(
                stop.wait(), timeout=S.DISPATCHER_SAFETY_INTERVAL_SECONDS
            )
        except asyncio.TimeoutError:
            continue


async def dispatch_pending(redis: ArqRedis) -> int:
    """Fetch pending jobs from the DB and enqueue them. Returns count enqueued."""
    sm = get_sessionmaker()

    def fetch() -> list[processor_service.PendingDispatchJob]:
        with sm() as db:
            return processor_service.collect_pending_jobs(
                db, batch_size=S.DISPATCHER_BATCH_SIZE
            )

    jobs = await asyncio.to_thread(fetch)
    if not jobs:
        return 0

    enqueued = 0
    for job in jobs:
        job_id = f"{job.processor_id}:{job.event_id}"
        result = await redis.enqueue_job(
            "run_processor_event",
            str(job.processor_id),
            str(job.event_id),
            _job_id=job_id,
        )
        if result is not None:
            enqueued += 1
            log.debug(
                "dispatcher_enqueued",
                processor_id=str(job.processor_id),
                event_id=str(job.event_id),
                offset=job.event_offset,
                event_type=job.event_type,
            )
    if enqueued:
        log.info(
            "dispatcher_tick",
            enqueued=enqueued,
            considered=len(jobs),
        )
    return enqueued


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()

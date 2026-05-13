"""Arq worker for the warm `relic:processing` queue.

Each job is one `(processor_id, event_id)` pair handed in by the dispatcher.
The handler is idempotent over the pair and advances the processor's cursor
on success only — see `services.processors.execute_processor_event`.
"""

import asyncio
import uuid

from database import get_sessionmaker
from processors.registry import init_builtin_substrates
from services import processors as processor_service
from infra.arq import arq_redis_settings

import settings as S

init_builtin_substrates()


async def run_processor_event(
    ctx, processor_id: str, event_id: str
) -> dict[str, object]:
    """Run one processor against one file event.

    Returns a small dict for arq's job result, useful when inspecting state
    via ``arq cli`` or scraping logs.
    """
    del ctx

    def run():
        sm = get_sessionmaker()
        return processor_service.execute_processor_event(
            sm,
            processor_id=uuid.UUID(processor_id),
            event_id=uuid.UUID(event_id),
        )

    result = await asyncio.to_thread(run)
    return {
        "status": result.status,
        "advanced_to_offset": result.advanced_to_offset,
        "duration_ms": result.duration_ms,
    }


class WorkerSettings:
    """arq worker that runs warm-path processor jobs.

    ``max_jobs = 1`` is intentional: per-processor concurrency is the contract,
    and the dispatcher already enforces it by only emitting one in-flight job
    per processor (``LIMIT 1`` per tick + ``_job_id`` dedup + ``SELECT FOR
    UPDATE`` on the processor row inside the worker). Setting arq concurrency
    to 1 closes the gap defensively so a future change to the dispatcher
    cannot accidentally violate concurrency. Scale by running more worker
    pods/containers, not more coroutines per worker.
    """

    functions = [run_processor_event]
    redis_settings = arq_redis_settings()
    queue_name = S.PROCESSING_QUEUE_NAME
    max_jobs = 1

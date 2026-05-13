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
from services.processor_queue import redis_settings

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
    functions = [run_processor_event]
    redis_settings = redis_settings()
    queue_name = S.PROCESSING_QUEUE_NAME

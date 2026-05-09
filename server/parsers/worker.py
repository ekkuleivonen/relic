import uuid

from database import get_sessionmaker
from parsers import base
from services.parser_queue import redis_settings

import settings as S


async def parse_file(ctx, file_id: str) -> None:
    del ctx
    with get_sessionmaker()() as db:
        base.parse_file(db, uuid.UUID(file_id))


class WorkerSettings:
    functions = [parse_file]
    redis_settings = redis_settings()
    queue_name = S.PARSER_QUEUE_NAME

import inspect
import time
from typing import Any

from arq import create_pool
from arq.connections import ArqRedis
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

import settings as S
from models import Bucket, Processor
from services.placement import bucket_is_healthy
from services.processor_queue import redis_settings

STATUS_OK = "ok"
STATUS_FAILED = "failed"


def health_response() -> dict[str, Any]:
    return {
        "status": STATUS_OK,
        "checks": {
            "api": {"status": STATUS_OK},
        },
    }


async def readiness_response(db: Session) -> dict[str, Any]:
    checks = {
        "database": check_database(db),
        "redis": await check_redis_queues(),
        "processors": check_processors(db),
        "object_stores": check_object_stores(db),
        "configuration": check_configuration(),
    }
    status = (
        STATUS_OK
        if all(check["status"] == STATUS_OK for check in checks.values())
        else STATUS_FAILED
    )
    return {"status": status, "checks": checks}


def check_database(db: Session) -> dict[str, Any]:
    try:
        db.execute(text("SELECT 1")).scalar_one()
    except Exception as exc:
        return failed_check(exc)
    return {"status": STATUS_OK}


async def check_redis_queues() -> dict[str, Any]:
    try:
        redis = await create_pool(
            redis_settings(),
            default_queue_name=S.PROCESSING_QUEUE_NAME,
        )
    except Exception as exc:
        return failed_check(exc)

    try:
        await redis.ping()
        queues = {
            S.PROCESSING_QUEUE_NAME: await queue_snapshot(redis, S.PROCESSING_QUEUE_NAME),
            S.MAINTENANCE_QUEUE_NAME: await queue_snapshot(
                redis, S.MAINTENANCE_QUEUE_NAME
            ),
        }
    except Exception as exc:
        return failed_check(exc)
    finally:
        await close_redis(redis)

    return {"status": STATUS_OK, "queues": queues}


async def queue_snapshot(redis: ArqRedis, queue_name: str) -> dict[str, Any]:
    depth = int(await redis.zcard(queue_name))
    oldest_age_seconds = None
    oldest = await redis.zrange(queue_name, 0, 0, withscores=True)
    if oldest:
        score = oldest[0][1]
        oldest_age_seconds = max(0.0, (time.time() * 1000 - float(score)) / 1000)
    return {
        "depth": depth,
        "oldest_pending_age_seconds": oldest_age_seconds,
    }


async def close_redis(redis: ArqRedis) -> None:
    close = getattr(redis, "close", None)
    if close is None:
        return
    result = close()
    if inspect.isawaitable(result):
        await result


def check_processors(db: Session) -> dict[str, Any]:
    try:
        enabled = db.scalar(
            select(func.count()).select_from(Processor).where(Processor.enabled.is_(True))
        )
        total = db.scalar(select(func.count()).select_from(Processor))
    except Exception as exc:
        return failed_check(exc)
    return {
        "status": STATUS_OK,
        "enabled": int(enabled or 0),
        "total": int(total or 0),
    }


def check_object_stores(db: Session) -> dict[str, Any]:
    try:
        buckets = list(db.scalars(select(Bucket).order_by(Bucket.name)))
    except Exception as exc:
        return failed_check(exc)

    unhealthy = [
        {"id": str(bucket.id), "name": bucket.name}
        for bucket in buckets
        if not bucket_is_healthy(bucket)
    ]
    return {
        "status": STATUS_FAILED if unhealthy else STATUS_OK,
        "configured": len(buckets),
        "healthy": len(buckets) - len(unhealthy),
        "unhealthy": unhealthy,
    }


def check_configuration() -> dict[str, Any]:
    warnings: list[str] = []
    if S.ENCRYPTION_SECRET == "dev-encryption-secret-change-me":
        warnings.append("ENCRYPTION_SECRET is using the local development default")
    if S.SESSION_SECRET == S.ENCRYPTION_SECRET:
        warnings.append("SESSION_SECRET is falling back to ENCRYPTION_SECRET")
    if S.REDIS_PASSWORD == "replace_me":
        warnings.append("REDIS_PASSWORD is using the local development default")
    if S.RELIC_ADMIN_PASSWORD == "relic-admin":
        warnings.append("RELIC_ADMIN_PASSWORD is using the local development default")

    return {
        "status": STATUS_OK,
        "warnings": warnings,
    }


def failed_check(exc: Exception) -> dict[str, Any]:
    return {
        "status": STATUS_FAILED,
        "error_class": exc.__class__.__name__,
        "error_message": str(exc),
    }

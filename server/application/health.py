import inspect
import time
from typing import Any

from arq import create_pool
from arq.connections import ArqRedis
from sqlalchemy import select, text
from sqlalchemy.orm import Session

import settings as S
from enums import HealthStatus
from infra.db.models import Bucket
from application.control_plane.placement import bucket_is_reachable
from infra.arq import arq_redis_settings


def health_response() -> dict[str, Any]:
    return {
        "status": HealthStatus.OK.value,
        "checks": {
            "api": {"status": HealthStatus.OK.value},
        },
    }


async def readiness_response(db: Session) -> dict[str, Any]:
    checks = {
        "database": check_database(db),
        "redis": await check_redis_queues(),
        "object_stores": check_object_stores(db),
        "configuration": check_configuration(),
    }
    status = (
        HealthStatus.OK.value
        if all(check["status"] == HealthStatus.OK.value for check in checks.values())
        else HealthStatus.FAILED.value
    )
    return {"status": status, "checks": checks}


def check_database(db: Session) -> dict[str, Any]:
    try:
        db.execute(text("SELECT 1")).scalar_one()
    except Exception as exc:
        return failed_check(exc)
    return {"status": HealthStatus.OK.value}


async def check_redis_queues() -> dict[str, Any]:
    try:
        redis = await create_pool(
            arq_redis_settings(),
            default_queue_name=S.MAINTENANCE_QUEUE_NAME,
        )
    except Exception as exc:
        return failed_check(exc)

    try:
        await redis.ping()
        queues = {
            S.MAINTENANCE_QUEUE_NAME: await queue_snapshot(
                redis, S.MAINTENANCE_QUEUE_NAME
            ),
        }
    except Exception as exc:
        return failed_check(exc)
    finally:
        await close_redis(redis)

    return {"status": HealthStatus.OK.value, "queues": queues}


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


def check_object_stores(db: Session) -> dict[str, Any]:
    try:
        buckets = list(db.scalars(select(Bucket).order_by(Bucket.name)))
    except Exception as exc:
        return failed_check(exc)

    unhealthy = [
        {"id": str(bucket.id), "name": bucket.name}
        for bucket in buckets
        if not bucket_is_reachable(db, bucket)
    ]
    return {
        "status": HealthStatus.FAILED.value if unhealthy else HealthStatus.OK.value,
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
        "status": HealthStatus.OK.value,
        "warnings": warnings,
    }


def failed_check(exc: Exception) -> dict[str, Any]:
    return {
        "status": HealthStatus.FAILED.value,
        "error_class": exc.__class__.__name__,
        "error_message": str(exc),
    }

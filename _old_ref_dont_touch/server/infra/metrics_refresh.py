"""Refresh Prometheus gauges at scrape time."""

from __future__ import annotations

from sqlalchemy import func, select, text

from infra import metrics
from infra.db.engine import get_engine, get_sessionmaker
from infra.db.models import Blob, File, StorageBackend
from infra.redis.client import get_redis_client
from infra.worker_heartbeats import maintenance_heartbeat_status
from utils.logging import get_logger

log = get_logger(__name__)


def refresh_scrape_gauges() -> None:
    for refresh in (
        refresh_db_pool_gauges,
        refresh_dependency_gauges,
        refresh_worker_heartbeat_gauge,
    ):
        try:
            refresh()
        except Exception as exc:
            log.warning(
                "metrics_scrape_refresh_failed",
                refresh=refresh.__name__,
                error=str(exc),
            )


def refresh_db_pool_gauges() -> None:
    pool = get_engine().pool
    metrics.DB_POOL_SIZE.set(pool.size())
    metrics.DB_POOL_CHECKED_OUT.set(pool.checkedout())
    metrics.DB_POOL_OVERFLOW.set(pool.overflow())


def refresh_dependency_gauges() -> None:
    metrics.set_dependency_up(dependency="postgres", up=_postgres_up())
    metrics.set_dependency_up(dependency="redis", up=_redis_up())
    maintenance = maintenance_heartbeat_status()
    metrics.set_dependency_up(
        dependency="workers",
        up=maintenance["status"] == "ok",
    )


def refresh_worker_heartbeat_gauge() -> None:
    maintenance = maintenance_heartbeat_status()
    age = maintenance.get("last_seen_seconds_ago")
    if age is not None:
        metrics.set_worker_heartbeat_age(worker="maintenance", age_seconds=float(age))


def refresh_business_gauges() -> None:
    try:
        _refresh_business_gauges()
    except Exception as exc:
        log.warning("metrics_business_refresh_failed", error=str(exc))


def _refresh_business_gauges() -> None:
    sm = get_sessionmaker()
    with sm() as db:
        files_total = int(db.scalar(select(func.count()).select_from(File)) or 0)
        blobs_total = int(
            db.scalar(
                select(func.count()).select_from(Blob).where(Blob.refcount > 0)
            )
            or 0
        )
        rows = db.execute(
            select(
                StorageBackend.kind,
                func.coalesce(func.sum(Blob.size_bytes), 0),
            )
            .join(Blob, Blob.storage_backend_id == StorageBackend.id)
            .where(Blob.refcount > 0)
            .group_by(StorageBackend.kind)
        ).all()
    storage_bytes_by_kind = {
        str(kind.value if hasattr(kind, "value") else kind): int(size_bytes)
        for kind, size_bytes in rows
    }
    metrics.refresh_business_gauges_from_stats(
        files_total=files_total,
        blobs_total=blobs_total,
        storage_bytes_by_kind=storage_bytes_by_kind,
    )


def _postgres_up() -> bool:
    try:
        sm = get_sessionmaker()
        with sm() as db:
            db.execute(text("SELECT 1")).scalar_one()
        return True
    except Exception as exc:
        log.debug("dependency_postgres_check_failed", error=str(exc))
        return False


def _redis_up() -> bool:
    try:
        return get_redis_client().ping()
    except Exception as exc:
        log.debug("dependency_redis_check_failed", error=str(exc))
        return False

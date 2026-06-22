"""Low-cardinality Prometheus metrics for app and worker health."""

from __future__ import annotations

import time
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

_API_DURATION_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)
_GATEWAY_DURATION_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
    60.0,
)
_OBJECT_SIZE_BUCKETS = (
    1024,
    64 * 1024,
    256 * 1024,
    1024 * 1024,
    4 * 1024 * 1024,
    16 * 1024 * 1024,
    64 * 1024 * 1024,
    256 * 1024 * 1024,
    1024 * 1024 * 1024,
)

API_REQUESTS = Counter(
    "relic_api_requests_total",
    "Total HTTP API requests.",
    ("method", "route", "status_class"),
)
API_DURATION = Histogram(
    "relic_api_duration_seconds",
    "HTTP API request duration.",
    ("method", "route"),
    buckets=_API_DURATION_BUCKETS,
)
API_INFLIGHT = Gauge(
    "relic_api_inflight_requests",
    "In-flight HTTP API requests.",
)
GATEWAY_REQUESTS = Counter(
    "relic_gateway_requests_total",
    "Total S3 gateway requests.",
    ("operation", "status_class"),
)
GATEWAY_DURATION = Histogram(
    "relic_gateway_duration_seconds",
    "S3 gateway request duration.",
    ("operation",),
    buckets=_GATEWAY_DURATION_BUCKETS,
)
GATEWAY_BYTES = Counter(
    "relic_gateway_bytes_total",
    "Total S3 gateway bytes transferred.",
    ("operation", "direction"),
)
GATEWAY_OBJECT_SIZE = Histogram(
    "relic_gateway_object_size_bytes",
    "S3 gateway object sizes.",
    ("operation",),
    buckets=_OBJECT_SIZE_BUCKETS,
)
MAINTENANCE_JOBS = Counter(
    "relic_maintenance_jobs_total",
    "Total maintenance worker jobs.",
    ("job", "status"),
)
MAINTENANCE_DURATION = Histogram(
    "relic_maintenance_duration_seconds",
    "Maintenance worker job duration.",
    ("job",),
)
MAINTENANCE_QUEUE_DEPTH = Gauge(
    "relic_maintenance_queue_depth",
    "Pending maintenance queue depth.",
    ("queue",),
)
MAINTENANCE_OPERATIONS = Counter(
    "relic_maintenance_operations_total",
    "Maintenance batch operation outcomes.",
    ("operation", "status"),
)
BUCKET_PROBES = Counter(
    "relic_storage_backend_probe_total",
    "StorageBackend probe outcomes.",
    ("status", "backend_type"),
)
AUTH_ATTEMPTS = Counter(
    "relic_auth_attempts_total",
    "Authentication attempts.",
    ("auth_type", "result"),
)
DEPENDENCY_UP = Gauge(
    "relic_dependency_up",
    "Dependency readiness (1=up, 0=down).",
    ("dependency",),
)
WORKER_HEARTBEAT_AGE = Gauge(
    "relic_worker_heartbeat_age_seconds",
    "Seconds since the worker last wrote a heartbeat.",
    ("worker",),
)
DB_POOL_SIZE = Gauge("relic_db_pool_size", "Current SQLAlchemy pool size.")
DB_POOL_CHECKED_OUT = Gauge(
    "relic_db_pool_checked_out",
    "SQLAlchemy pool connections currently checked out.",
)
DB_POOL_OVERFLOW = Gauge(
    "relic_db_pool_overflow",
    "SQLAlchemy pool overflow connection count.",
)
DB_QUERY_DURATION = Histogram(
    "relic_db_query_duration_seconds",
    "Database query duration.",
    buckets=_API_DURATION_BUCKETS,
)
REDIS_COMMAND_DURATION = Histogram(
    "relic_redis_command_duration_seconds",
    "Redis command duration.",
    ("command",),
    buckets=_API_DURATION_BUCKETS,
)
ARQ_JOBS_ENQUEUED = Counter(
    "relic_arq_jobs_enqueued_total",
    "Total ARQ jobs enqueued.",
    ("job",),
)
FILES_TOTAL = Gauge("relic_files_total", "Total file rows.")
BLOBS_TOTAL = Gauge("relic_blobs_total", "Total live blob rows (refcount > 0).")
STORAGE_BYTES = Gauge(
    "relic_storage_bytes",
    "Total live blob bytes grouped by backend kind.",
    ("backend_kind",),
)


def metrics_body() -> bytes:
    from infra.metrics_refresh import refresh_scrape_gauges

    refresh_scrape_gauges()
    return generate_latest()


def metrics_content_type() -> str:
    return CONTENT_TYPE_LATEST


def timer_start() -> float:
    return time.perf_counter()


def observe_api_request(
    *,
    method: str,
    route: str,
    status_code: int,
    started_at: float,
) -> None:
    status_class = _status_class(status_code)
    API_REQUESTS.labels(method=method, route=route, status_class=status_class).inc()
    API_DURATION.labels(method=method, route=route).observe(_elapsed(started_at))


def observe_gateway_request(
    *, operation: str, status_code: int, started_at: float
) -> None:
    status_class = _status_class(status_code)
    GATEWAY_REQUESTS.labels(operation=operation, status_class=status_class).inc()
    GATEWAY_DURATION.labels(operation=operation).observe(_elapsed(started_at))


def observe_gateway_bytes(*, operation: str, direction: str, bytes_count: int) -> None:
    if bytes_count <= 0:
        return
    GATEWAY_BYTES.labels(operation=operation, direction=direction).inc(bytes_count)


def observe_gateway_object_size(*, operation: str, size_bytes: int) -> None:
    if size_bytes <= 0:
        return
    GATEWAY_OBJECT_SIZE.labels(operation=operation).observe(size_bytes)


def observe_maintenance_job(*, job: str, status: str, started_at: float) -> None:
    MAINTENANCE_JOBS.labels(job=job, status=status).inc()
    MAINTENANCE_DURATION.labels(job=job).observe(_elapsed(started_at))


def set_maintenance_queue_depth(*, queue: str, depth: int) -> None:
    MAINTENANCE_QUEUE_DEPTH.labels(queue=queue).set(depth)


def observe_storage_backend_probe(*, status: str, backend_type: str) -> None:
    BUCKET_PROBES.labels(status=status, backend_type=backend_type).inc()


def observe_auth_attempt(*, auth_type: str, result: str) -> None:
    AUTH_ATTEMPTS.labels(auth_type=auth_type, result=result).inc()


def set_dependency_up(*, dependency: str, up: bool) -> None:
    DEPENDENCY_UP.labels(dependency=dependency).set(1 if up else 0)


def set_worker_heartbeat_age(*, worker: str, age_seconds: float) -> None:
    WORKER_HEARTBEAT_AGE.labels(worker=worker).set(max(0.0, age_seconds))


def observe_redis_command(*, command: str, started_at: float) -> None:
    REDIS_COMMAND_DURATION.labels(command=command).observe(_elapsed(started_at))


def observe_arq_job_enqueued(*, job: str) -> None:
    ARQ_JOBS_ENQUEUED.labels(job=job).inc()


def observe_maintenance_batch_result(*, job: str, stats: dict[str, Any]) -> None:
    if job == "purge_dereferenced_blobs":
        deleted_rows = int(stats.get("deleted_rows", 0))
        errors = int(stats.get("errors", 0))
        if deleted_rows:
            MAINTENANCE_OPERATIONS.labels(
                operation="purge_dereferenced_blobs",
                status="succeeded",
            ).inc(deleted_rows)
        if errors:
            MAINTENANCE_OPERATIONS.labels(
                operation="purge_dereferenced_blobs",
                status="failed",
            ).inc(errors)
        return

    operation_map = {
        "demote_pressured_buckets": "demote",
        "promote_recently_accessed": "promote",
    }
    operation = operation_map.get(job)
    if operation is None:
        return

    for status in ("moved", "skipped", "failed"):
        count = int(stats.get(status, 0))
        if count:
            MAINTENANCE_OPERATIONS.labels(operation=operation, status=status).inc(count)


def refresh_business_gauges_from_stats(
    *,
    files_total: int,
    blobs_total: int,
    storage_bytes_by_kind: dict[str, int],
) -> None:
    FILES_TOTAL.set(files_total)
    BLOBS_TOTAL.set(blobs_total)
    for backend_kind, size_bytes in storage_bytes_by_kind.items():
        STORAGE_BYTES.labels(backend_kind=backend_kind).set(size_bytes)


def _elapsed(started_at: float) -> float:
    return max(0.0, time.perf_counter() - started_at)


def _status_class(status_code: int) -> str:
    return f"{status_code // 100}xx"

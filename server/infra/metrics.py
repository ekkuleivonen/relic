"""Low-cardinality Prometheus metrics for app and worker health."""

from __future__ import annotations

import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest


API_REQUESTS = Counter(
    "relic_api_requests_total",
    "Total HTTP API requests.",
    ("method", "route", "status_class"),
)
API_DURATION = Histogram(
    "relic_api_duration_seconds",
    "HTTP API request duration.",
    ("method", "route"),
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
BUCKET_PROBES = Counter(
    "relic_bucket_probe_total",
    "Bucket probe outcomes.",
    ("status",),
)


def metrics_body() -> bytes:
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


def observe_maintenance_job(*, job: str, status: str, started_at: float) -> None:
    MAINTENANCE_JOBS.labels(job=job, status=status).inc()
    MAINTENANCE_DURATION.labels(job=job).observe(_elapsed(started_at))


def set_maintenance_queue_depth(*, queue: str, depth: int) -> None:
    MAINTENANCE_QUEUE_DEPTH.labels(queue=queue).set(depth)


def observe_bucket_probe(*, status: str) -> None:
    BUCKET_PROBES.labels(status=status).inc()


def _elapsed(started_at: float) -> float:
    return max(0.0, time.perf_counter() - started_at)


def _status_class(status_code: int) -> str:
    return f"{status_code // 100}xx"

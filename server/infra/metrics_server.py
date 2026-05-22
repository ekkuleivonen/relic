"""Prometheus metrics HTTP server for background workers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import settings as S
from utils.logging import get_logger

if TYPE_CHECKING:
    from wsgiref.simple_server import WSGIServer

log = get_logger(__name__)

_metrics_server: WSGIServer | None = None


def start_worker_metrics_server() -> None:
    global _metrics_server
    if not S.METRICS_WORKER_ENABLED:
        return
    if _metrics_server is not None:
        return
    from prometheus_client import start_http_server

    _metrics_server = start_http_server(S.METRICS_WORKER_PORT, addr="0.0.0.0")
    log.info("worker_metrics_server_started", port=S.METRICS_WORKER_PORT)


def stop_worker_metrics_server() -> None:
    global _metrics_server
    if _metrics_server is None:
        return
    _metrics_server.shutdown()
    _metrics_server = None
    log.info("worker_metrics_server_stopped")

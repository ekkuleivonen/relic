"""SQLAlchemy pool and query latency instrumentation."""

from __future__ import annotations

import time

from sqlalchemy import event
from sqlalchemy.engine import Engine

from infra import metrics


def install_db_metrics(engine: Engine) -> None:
    if getattr(engine, "_pithosys_metrics_installed", False):
        return
    engine._pithosys_metrics_installed = True  # type: ignore[attr-defined]

    @event.listens_for(engine, "before_cursor_execute")
    def _before_cursor_execute(
        conn, cursor, statement, parameters, context, executemany
    ) -> None:
        conn.info.setdefault("query_start_time", []).append(time.perf_counter())

    @event.listens_for(engine, "after_cursor_execute")
    def _after_cursor_execute(
        conn, cursor, statement, parameters, context, executemany
    ) -> None:
        started_at = conn.info.get("query_start_time", []).pop()
        metrics.DB_QUERY_DURATION.observe(max(0.0, time.perf_counter() - started_at))

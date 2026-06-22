"""Worker startup/shutdown hooks for maintenance metrics."""

from __future__ import annotations

import pytest

from infra.metrics_server import start_worker_metrics_server, stop_worker_metrics_server
import infra.metrics_server as metrics_server_module


@pytest.fixture(autouse=True)
def _reset_metrics_server():
    stop_worker_metrics_server()
    metrics_server_module._metrics_server = None
    yield
    stop_worker_metrics_server()
    metrics_server_module._metrics_server = None


def test_worker_startup_starts_metrics_server(monkeypatch):
    import workers.maintenance as maintenance_worker

    captured: dict[str, object] = {}

    def fake_start() -> None:
        captured["started"] = True

    monkeypatch.setattr(maintenance_worker, "start_worker_metrics_server", fake_start)

    import asyncio

    asyncio.run(maintenance_worker.worker_startup({}))

    assert captured.get("started") is True


def test_worker_shutdown_stops_metrics_server(monkeypatch):
    import workers.maintenance as maintenance_worker

    captured: dict[str, object] = {}

    def fake_stop() -> None:
        captured["stopped"] = True

    monkeypatch.setattr(maintenance_worker, "stop_worker_metrics_server", fake_stop)

    import asyncio

    asyncio.run(maintenance_worker.worker_shutdown({}))

    assert captured.get("stopped") is True


def test_start_worker_metrics_server_is_idempotent(monkeypatch):
    monkeypatch.setattr("infra.metrics_server.S.METRICS_WORKER_ENABLED", True)
    monkeypatch.setattr("infra.metrics_server.S.METRICS_WORKER_PORT", 19100)

    calls = {"count": 0}

    def fake_start_http_server(port, addr):
        calls["count"] += 1
        return type("Server", (), {"shutdown": lambda self: None})()

    monkeypatch.setattr(
        "prometheus_client.start_http_server",
        fake_start_http_server,
    )

    start_worker_metrics_server()
    start_worker_metrics_server()

    assert calls["count"] == 1


def test_start_worker_metrics_server_skips_when_disabled(monkeypatch):
    monkeypatch.setattr("infra.metrics_server.S.METRICS_WORKER_ENABLED", False)

    start_worker_metrics_server()

    assert metrics_server_module._metrics_server is None

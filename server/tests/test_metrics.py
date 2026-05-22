"""Prometheus metrics instrumentation tests."""

from __future__ import annotations

import uuid

import pytest

from infra import metrics
from infra.auth.s3_signing import S3SigningError, verify_request
from infra.gateway import blob_storage
from infra.metrics_refresh import refresh_business_gauges, refresh_scrape_gauges
from tests.factories.models import BlobFactory, FolderFactory, StorageBackendFactory, UserFactory
from infra.db.models import File


class _TestSessionMaker:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return _TestSessionContext(self._session)


class _TestSessionContext:
    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, *args):
        return False


def test_metrics_endpoint_exposes_core_series(client):
    client.get("/healthz")

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    body = response.text
    assert "relic_api_requests_total" in body
    assert "relic_dependency_up" in body
    assert "relic_db_pool_size" in body
    assert "relic_worker_heartbeat_age_seconds" in body
    assert "relic_api_inflight_requests" in body


def test_s3_requests_use_gateway_metrics_only(client, monkeypatch):
    monkeypatch.setattr(
        "api.s3.helpers.load_signed_user",
        lambda request, db: type("User", (), {"id": uuid.uuid4()})(),
    )

    response = client.get("/s3")

    assert response.status_code in {200, 400, 403, 404, 405}
    body = client.get("/metrics").text
    assert "relic_gateway_requests_total" in body
    assert 'route="/s3"' not in body


def test_observe_storage_backend_probe_includes_backend_type():
    metrics.observe_storage_backend_probe(status="succeeded", backend_type="s3")

    output = metrics.metrics_body().decode()
    assert 'relic_storage_backend_probe_total{backend_type="s3",status="succeeded"}' in output


def test_observe_maintenance_batch_result_records_tier_movements():
    metrics.observe_maintenance_batch_result(
        job="demote_pressured_buckets",
        stats={"moved": 2, "skipped": 1, "failed": 3},
    )

    output = metrics.metrics_body().decode()
    assert 'relic_maintenance_operations_total{operation="demote",status="moved"} 2.0' in output
    assert 'relic_maintenance_operations_total{operation="demote",status="failed"} 3.0' in output


def test_observe_gateway_bytes_and_object_size():
    metrics.observe_gateway_bytes(
        operation="put_object",
        direction="write",
        bytes_count=4096,
    )
    metrics.observe_gateway_object_size(operation="put_object", size_bytes=4096)

    output = metrics.metrics_body().decode()
    assert "relic_gateway_bytes_total" in output
    assert "relic_gateway_object_size_bytes" in output


def test_s3_signing_failure_records_auth_metric():
    request = type(
        "Request",
        (),
        {
            "headers": {},
            "query_params": {},
        },
    )()

    with pytest.raises(S3SigningError):
        verify_request(request, db=None)  # type: ignore[arg-type]

    output = metrics.metrics_body().decode()
    assert 'relic_auth_attempts_total{auth_type="s3",result="failed"}' in output


def test_refresh_business_gauges(db_session, monkeypatch):
    monkeypatch.setattr(
        "infra.metrics_refresh.get_sessionmaker",
        lambda: _TestSessionMaker(db_session),
    )
    backend = StorageBackendFactory()
    db_session.add(backend)
    db_session.flush()
    blob = BlobFactory(storage_backend_id=backend.id, size_bytes=1024, refcount=1)
    db_session.add(blob)
    db_session.flush()
    folder = FolderFactory()
    db_session.add(folder)
    db_session.flush()
    user = UserFactory()
    db_session.add(user)
    db_session.flush()
    db_session.add(
        File(
            folder_id=folder.id,
            blob_id=blob.id,
            actor_id=user.id,
            name="metrics-test.bin",
        )
    )
    db_session.commit()

    refresh_business_gauges()

    output = metrics.metrics_body().decode()
    assert "relic_files_total 1.0" in output
    assert "relic_blobs_total 1.0" in output
    assert 'relic_storage_bytes{backend_kind="s3"} 1024.0' in output


def test_blob_storage_upload_records_bytes():
    class FakeAdapter:
        def put(self, *, namespace, key, body, size):
            del namespace, key, body, size

    class FakeRegistry:
        def for_storage_backend(self, bucket):
            del bucket
            return FakeAdapter()

    import io

    body = io.BytesIO(b"hello")
    bucket = type("Bucket", (), {"namespace": "ns"})()
    blob_storage.upload_blob(
        storage=FakeRegistry(),
        bucket=bucket,
        bucket_key="key",
        body=body,
        operation="put_object",
    )

    output = metrics.metrics_body().decode()
    assert "relic_gateway_bytes_total" in output
    assert 'operation="put_object"' in output
    assert " 5.0" in output


def test_refresh_scrape_gauges_sets_dependency_series(monkeypatch):
    monkeypatch.setattr("infra.metrics_refresh._postgres_up", lambda: True)
    monkeypatch.setattr("infra.metrics_refresh._redis_up", lambda: True)
    monkeypatch.setattr(
        "infra.metrics_refresh.maintenance_heartbeat_status",
        lambda: {"status": "ok", "last_seen_seconds_ago": 12.5},
    )
    monkeypatch.setattr(
        "infra.metrics_refresh.get_engine",
        lambda: type(
            "Engine",
            (),
            {
                "pool": type(
                    "Pool",
                    (),
                    {
                        "size": lambda self: 5,
                        "checkedout": lambda self: 1,
                        "overflow": lambda self: 0,
                    },
                )()
            },
        )(),
    )

    refresh_scrape_gauges()

    output = metrics.metrics_body().decode()
    assert 'relic_dependency_up{dependency="postgres"} 1.0' in output
    assert 'relic_dependency_up{dependency="redis"} 1.0' in output
    assert 'relic_worker_heartbeat_age_seconds{worker="maintenance"} 12.5' in output

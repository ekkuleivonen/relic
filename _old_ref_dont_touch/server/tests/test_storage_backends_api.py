import uuid

import pytest
from api.app import app
from infra.db.engine import get_db
from enums import UserRole
from fastapi.testclient import TestClient
from infra.db.models import Base, StorageBackend, User
from infra.db.stores.auth import create_session_token
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from tests.factories.models import BlobFactory, StorageBackendFactory
from utils.passwords import hash_password
from utils.secrets import MASKED_SECRET



@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    admin = User(
        name="Admin",
        email="admin@pithosys.local",
        password_hash=hash_password("password"),
        role=UserRole.ADMIN,
    )
    db_session.add(admin)
    db_session.commit()
    try:
        with TestClient(app) as test_client:
            test_client.cookies.set("pithosys_session", create_session_token(admin))
            yield test_client
    finally:
        app.dependency_overrides.clear()


def bucket_payload(name: str = "garage-hot") -> dict:
    bucket = StorageBackendFactory.build(name=name)
    return {
        "name": bucket.name,
        "endpoint": bucket.endpoint,
        "region": bucket.region,
        "namespace": bucket.namespace,
        "key_id": bucket.key_id,
        "secret_access_key": bucket.secret_access_key,
        "max_size_bytes": bucket.max_size_bytes,
    }


def test_create_and_list_storage_backends(client):
    payload = bucket_payload()
    create_response = client.post("/api/storage-backends/", json=payload)

    assert create_response.status_code == 200
    created = create_response.json()
    assert created["name"] == "garage-hot"
    assert created["namespace"] == "blobs"
    assert created["key_id"] == "****" + payload["key_id"][-4:]
    assert created["secret_access_key"] == MASKED_SECRET
    assert created["max_size_bytes"] == 1_000_000_000
    assert created["kind"] == "s3"
    assert created["object_count"] == 0
    assert created["current_size_bytes"] == 0

    list_response = client.get("/api/storage-backends/")

    assert list_response.status_code == 200
    assert [bucket["name"] for bucket in list_response.json()] == ["garage-hot"]


def test_create_storage_backend_rejects_duplicate_name(client):
    assert client.post("/api/storage-backends/", json=bucket_payload()).status_code == 200

    response = client.post("/api/storage-backends/", json=bucket_payload())

    assert response.status_code == 409


def test_create_filesystem_bucket(client, tmp_path):
    payload = {
        "name": "hot-nvme",
        "endpoint": str(tmp_path),
        "namespace": "blobs",
        "max_size_bytes": 500_000_000_000,
        "kind": "filesystem",
    }
    response = client.post("/api/storage-backends/", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "filesystem"
    assert body["endpoint"] == str(tmp_path)
    assert body["region"] == "local"
    assert body["key_id"] == "****stem"
    assert body["reachable"] is False


def test_create_filesystem_bucket_rejects_relative_path(client):
    response = client.post(
        "/api/storage-backends/",
        json={
            "name": "bad-path",
            "endpoint": "relative/path",
            "namespace": "blobs",
            "max_size_bytes": 1_000_000_000,
            "kind": "filesystem",
        },
    )

    assert response.status_code == 422


def test_update_storage_backend_rejects_kind_change(client):
    storage_backend_id = client.post("/api/storage-backends/", json=bucket_payload()).json()["id"]

    response = client.patch(
        f"/api/storage-backends/{storage_backend_id}",
        json={"kind": "filesystem"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Cannot change storage backend kind after creation"


def test_get_and_update_storage_backend(client):
    storage_backend_id = client.post("/api/storage-backends/", json=bucket_payload()).json()["id"]

    get_response = client.get(f"/api/storage-backends/{storage_backend_id}")
    assert get_response.status_code == 200
    assert get_response.json()["region"] == "garage"

    update_response = client.patch(
        f"/api/storage-backends/{storage_backend_id}",
        json={
            "name": "garage-hot-renamed",
            "endpoint": "http://garage-hot:3900",
            "region": "garage-renamed",
            "namespace": "blobs-renamed",
            "max_size_bytes": 2_000_000_000,
        },
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["name"] == "garage-hot-renamed"
    assert updated["endpoint"] == "http://garage-hot:3900"
    assert updated["region"] == "garage-renamed"
    assert updated["namespace"] == "blobs-renamed"
    assert updated["max_size_bytes"] == 2_000_000_000


def test_bucket_usage_is_derived_from_blobs(client, db_session):
    storage_backend_id = uuid.UUID(
        client.post("/api/storage-backends/", json=bucket_payload()).json()["id"]
    )
    db_session.add(BlobFactory(storage_backend_id=storage_backend_id, size_bytes=12))
    db_session.add(BlobFactory(storage_backend_id=storage_backend_id, size_bytes=30))
    db_session.commit()

    response = client.get(f"/api/storage-backends/{storage_backend_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["object_count"] == 2
    assert body["current_size_bytes"] == 42


def test_bucket_read_responses_mask_credentials(client):
    payload = bucket_payload()
    storage_backend_id = client.post("/api/storage-backends/", json=payload).json()["id"]

    get_response = client.get(f"/api/storage-backends/{storage_backend_id}")
    listed = client.get("/api/storage-backends/").json()

    assert get_response.status_code == 200
    body = get_response.json()
    assert body["key_id"] == "****" + payload["key_id"][-4:]
    assert body["secret_access_key"] == MASKED_SECRET
    assert payload["secret_access_key"] not in body["secret_access_key"]
    assert listed[0]["secret_access_key"] == MASKED_SECRET


def test_bucket_credentials_are_encrypted_at_rest(client, db_session):
    storage_backend_id = uuid.UUID(
        client.post("/api/storage-backends/", json=bucket_payload()).json()["id"]
    )
    bucket_row = db_session.get(StorageBackend, storage_backend_id)

    assert bucket_row.key_id.startswith("GK")
    assert bucket_row.secret_access_key.startswith("secret-")
    assert bucket_row._key_id != bucket_row.key_id
    assert bucket_row._secret_access_key != bucket_row.secret_access_key


def test_delete_storage_backend(client):
    storage_backend_id = client.post("/api/storage-backends/", json=bucket_payload()).json()["id"]

    delete_response = client.delete(f"/api/storage-backends/{storage_backend_id}")

    assert delete_response.status_code == 204
    assert client.get(f"/api/storage-backends/{storage_backend_id}").status_code == 404


def test_delete_storage_backend_with_blobs_returns_conflict(client, db_session):
    storage_backend_id = uuid.UUID(
        client.post("/api/storage-backends/", json=bucket_payload()).json()["id"]
    )
    db_session.add(BlobFactory(storage_backend_id=storage_backend_id))
    db_session.commit()

    response = client.delete(f"/api/storage-backends/{storage_backend_id}")

    assert response.status_code == 409
    assert response.json()["detail"]["blob_count"] == 1


def test_probe_storage_backend_records_probe_sample(client, db_session, monkeypatch):
    class FakeS3Client:
        def put_object(self, Bucket, Key, Body):
            return None

        def head_object(self, Bucket, Key):
            return None

        def get_object(self, Bucket, Key):
            class Body:
                def read(self):
                    return b"pithosys-probe"

            return {"Body": Body()}

        def delete_object(self, Bucket, Key):
            return None

    def fake_client(*args, **kwargs):
        return FakeS3Client()

    monkeypatch.setattr("infra.db.stores.storage_backend_probe.boto3.client", fake_client)
    storage_backend_id = client.post("/api/storage-backends/", json=bucket_payload()).json()["id"]

    response = client.post(f"/api/storage-backends/{storage_backend_id}/probe")

    assert response.status_code == 200
    body = response.json()
    assert body["reachable"] is True
    assert body["probe_sample_count"] >= 1
    assert body["avg_latency_ms"] is not None and body["avg_latency_ms"] >= 0

    probes = client.get(f"/api/storage-backends/{storage_backend_id}/probes").json()
    assert len(probes) == 1
    sample = probes[0]
    assert sample["success"] is True
    for key in ("put_ms", "head_ms", "get_ms", "delete_ms"):
        assert sample[key] is not None and sample[key] >= 0


def test_probe_filesystem_bucket(client, tmp_path):
    storage_backend_id = client.post(
        "/api/storage-backends/",
        json={
            "name": "local-hot",
            "endpoint": str(tmp_path),
            "namespace": "blobs",
            "max_size_bytes": 1_000_000_000,
            "kind": "filesystem",
        },
    ).json()["id"]

    response = client.post(f"/api/storage-backends/{storage_backend_id}/probe")

    assert response.status_code == 200
    body = response.json()
    assert body["reachable"] is True
    assert body["probe_sample_count"] >= 1
    assert body["avg_latency_ms"] is not None and body["avg_latency_ms"] >= 0

    probes = client.get(f"/api/storage-backends/{storage_backend_id}/probes").json()
    assert len(probes) == 1
    assert probes[0]["success"] is True


import uuid

import pytest
from api.app import app
from infra.db.engine import get_db
from enums import UserRole
from fastapi.testclient import TestClient
from infra.db.models import Base, Bucket, User
from application.control_plane.auth import create_session_token
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from tests.factories.models import BlobFactory, BucketFactory
from utils.passwords import hash_password



@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    admin = User(
        name="Admin",
        email="admin@relic.local",
        password_hash=hash_password("password"),
        role=UserRole.ADMIN,
    )
    db_session.add(admin)
    db_session.commit()
    try:
        with TestClient(app) as test_client:
            test_client.cookies.set("relic_session", create_session_token(admin))
            yield test_client
    finally:
        app.dependency_overrides.clear()


def bucket_payload(name: str = "garage-hot") -> dict:
    bucket = BucketFactory.build(name=name)
    return {
        "name": bucket.name,
        "endpoint": bucket.endpoint,
        "region": bucket.region,
        "bucket": bucket.bucket,
        "key_id": bucket.key_id,
        "secret_access_key": bucket.secret_access_key,
        "max_size_bytes": bucket.max_size_bytes,
    }


def test_create_and_list_buckets(client):
    create_response = client.post("/api/buckets/", json=bucket_payload())

    assert create_response.status_code == 200
    created = create_response.json()
    assert created["name"] == "garage-hot"
    assert created["bucket"] == "blobs"
    assert created["key_id"].startswith("GK")
    assert created["secret_access_key"].startswith("secret-")
    assert created["max_size_bytes"] == 1_000_000_000
    assert created["object_count"] == 0
    assert created["current_size_bytes"] == 0

    list_response = client.get("/api/buckets/")

    assert list_response.status_code == 200
    assert [bucket["name"] for bucket in list_response.json()] == ["garage-hot"]


def test_create_bucket_rejects_duplicate_name(client):
    assert client.post("/api/buckets/", json=bucket_payload()).status_code == 200

    response = client.post("/api/buckets/", json=bucket_payload())

    assert response.status_code == 409


def test_get_and_update_bucket(client):
    bucket_id = client.post("/api/buckets/", json=bucket_payload()).json()["id"]

    get_response = client.get(f"/api/buckets/{bucket_id}")
    assert get_response.status_code == 200
    assert get_response.json()["region"] == "garage"

    update_response = client.patch(
        f"/api/buckets/{bucket_id}",
        json={
            "name": "garage-hot-renamed",
            "endpoint": "http://garage-hot:3900",
            "region": "garage-renamed",
            "bucket": "blobs-renamed",
            "max_size_bytes": 2_000_000_000,
        },
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["name"] == "garage-hot-renamed"
    assert updated["endpoint"] == "http://garage-hot:3900"
    assert updated["region"] == "garage-renamed"
    assert updated["bucket"] == "blobs-renamed"
    assert updated["max_size_bytes"] == 2_000_000_000


def test_bucket_usage_is_derived_from_blobs(client, db_session):
    bucket_id = uuid.UUID(
        client.post("/api/buckets/", json=bucket_payload()).json()["id"]
    )
    db_session.add(BlobFactory(bucket_id=bucket_id, size_bytes=12))
    db_session.add(BlobFactory(bucket_id=bucket_id, size_bytes=30))
    db_session.commit()

    response = client.get(f"/api/buckets/{bucket_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["object_count"] == 2
    assert body["current_size_bytes"] == 42


def test_bucket_credentials_are_encrypted_at_rest(client, db_session):
    bucket_id = uuid.UUID(
        client.post("/api/buckets/", json=bucket_payload()).json()["id"]
    )
    bucket_row = db_session.get(Bucket, bucket_id)

    assert bucket_row.key_id.startswith("GK")
    assert bucket_row.secret_access_key.startswith("secret-")
    assert bucket_row._key_id != bucket_row.key_id
    assert bucket_row._secret_access_key != bucket_row.secret_access_key


def test_delete_bucket(client):
    bucket_id = client.post("/api/buckets/", json=bucket_payload()).json()["id"]

    delete_response = client.delete(f"/api/buckets/{bucket_id}")

    assert delete_response.status_code == 204
    assert client.get(f"/api/buckets/{bucket_id}").status_code == 404


def test_delete_bucket_with_blobs_returns_conflict(client, db_session):
    bucket_id = uuid.UUID(
        client.post("/api/buckets/", json=bucket_payload()).json()["id"]
    )
    db_session.add(BlobFactory(bucket_id=bucket_id))
    db_session.commit()

    response = client.delete(f"/api/buckets/{bucket_id}")

    assert response.status_code == 409
    assert response.json()["detail"]["blob_count"] == 1


def test_probe_bucket_records_probe_sample(client, db_session, monkeypatch):
    class FakeS3Client:
        def put_object(self, Bucket, Key, Body):
            return None

        def head_object(self, Bucket, Key):
            return None

        def get_object(self, Bucket, Key):
            class Body:
                def read(self):
                    return b"relic-probe"

            return {"Body": Body()}

        def delete_object(self, Bucket, Key):
            return None

    def fake_client(*args, **kwargs):
        return FakeS3Client()

    monkeypatch.setattr("application.control_plane.bucket_mutations.boto3.client", fake_client)
    bucket_id = client.post("/api/buckets/", json=bucket_payload()).json()["id"]

    response = client.post(f"/api/buckets/{bucket_id}/probe")

    assert response.status_code == 200
    body = response.json()
    assert body["reachable"] is True
    assert body["probe_sample_count"] >= 1
    assert body["avg_latency_ms"] is not None and body["avg_latency_ms"] >= 0

    probes = client.get(f"/api/buckets/{bucket_id}/probes").json()
    assert len(probes) == 1
    sample = probes[0]
    assert sample["success"] is True
    for key in ("put_ms", "head_ms", "get_ms", "delete_ms"):
        assert sample[key] is not None and sample[key] >= 0


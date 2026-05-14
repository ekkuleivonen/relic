import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.app import app
from enums import HealthStatus
from database import get_db
from models import Base
from services import health as health_service
from tests.factories.models import BucketFactory, BucketProbeFactory, ProcessorFactory


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with SessionLocal() as session:
        yield session


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def stub_redis(monkeypatch):
    async def check_redis_queues():
        return {
            "status": HealthStatus.OK,
            "queues": {
                "relic:processing": {"depth": 0, "oldest_pending_age_seconds": None},
                "relic:maintenance": {"depth": 0, "oldest_pending_age_seconds": None},
            },
        }

    monkeypatch.setattr(health_service, "check_redis_queues", check_redis_queues)


def test_healthz_reports_api_ok(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"api": {"status": "ok"}},
    }


def test_readyz_reports_dependency_status(client, db_session):
    bucket = BucketFactory.build()
    processor = ProcessorFactory.build(name="file_info")
    db_session.add_all([bucket, processor])
    db_session.flush()
    db_session.add(BucketProbeFactory.build(bucket_id=bucket.id))
    db_session.commit()

    response = client.get("/readyz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"]["status"] == "ok"
    assert body["checks"]["redis"]["status"] == "ok"
    assert body["checks"]["processors"] == {
        "status": "ok",
        "enabled": 1,
        "total": 1,
    }
    assert body["checks"]["object_stores"] == {
        "status": "ok",
        "configured": 1,
        "healthy": 1,
        "unhealthy": [],
    }
    assert body["checks"]["configuration"]["status"] == "ok"


def test_readyz_returns_unavailable_for_unhealthy_object_store(client, db_session):
    bucket = BucketFactory.build(name="unprobed")
    db_session.add(bucket)
    db_session.commit()

    response = client.get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "failed"
    assert body["checks"]["object_stores"]["status"] == "failed"
    assert body["checks"]["object_stores"]["unhealthy"] == [
        {"id": str(bucket.id), "name": "unprobed"}
    ]


def test_readyz_returns_unavailable_for_redis_failure(client, monkeypatch):
    async def check_redis_queues():
        return {
            "status": HealthStatus.FAILED,
            "error_class": "ConnectionError",
            "error_message": "redis down",
        }

    monkeypatch.setattr(health_service, "check_redis_queues", check_redis_queues)

    response = client.get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "failed"
    assert body["checks"]["redis"] == {
        "status": "failed",
        "error_class": "ConnectionError",
        "error_message": "redis down",
    }

"""Shared test fixtures."""

import pytest
from api.app import app
from infra.cache import folder_access as folder_access_cache
from infra.db.stores.placement import clear_bucket_usage_cache
from fastapi.testclient import TestClient
from infra.db.engine import get_db
from sqlalchemy.orm import sessionmaker
from tests.db import create_test_engine, upgrade_test_schema


@pytest.fixture(autouse=True)
def _clear_folder_access_caches():
    folder_access_cache.clear_hotpath_cache(None)
    yield
    folder_access_cache.clear_hotpath_cache(None)


@pytest.fixture()
def db_session():
    clear_bucket_usage_cache()
    engine = create_test_engine()
    upgrade_test_schema(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with SessionLocal() as session:
        folder_access_cache.clear_hotpath_cache(session)
        yield session
        folder_access_cache.clear_hotpath_cache(session)
    clear_bucket_usage_cache()


@pytest.fixture()
def storage_registry():
    from composition import build_storage_registry

    return build_storage_registry()


@pytest.fixture()
def run_uow(db_session):
    from application.uow_runner import run_with_uow

    def _run(fn):
        return run_with_uow(db_session, fn)

    return _run


@pytest.fixture()
def client(db_session):
    """Unauthenticated API client with the shared in-memory DB session."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()

import hashlib

import pytest
from infra.gateway import object_writes
from enums import UserRole
from infra.db.models import Folder
from tests.factories.models import StorageBackendFactory, StorageBackendProbeFactory, UserFactory
from tests.fakes.memory_storage_registry import MemoryStorageRegistry


@pytest.fixture()
def root_folder(db_session):
    root = Folder(name="", parent_id=None)
    db_session.add(root)
    db_session.commit()
    return root


@pytest.fixture()
def photos_folder(db_session, root_folder):
    folder = Folder(name="photos", parent_id=root_folder.id)
    db_session.add(folder)
    db_session.commit()
    return folder


def _add_bucket(db_session, **overrides):
    bucket = StorageBackendFactory.build(**overrides)
    db_session.add(bucket)
    db_session.flush()
    db_session.add(
        StorageBackendProbeFactory.build(
            storage_backend_id=bucket.id,
            put_ms=5,
            head_ms=5,
            get_ms=5,
            delete_ms=5,
        )
    )
    db_session.commit()
    db_session.refresh(bucket)
    return bucket


def test_put_object_with_memory_storage(db_session, photos_folder):
    _add_bucket(db_session, name="hot")
    storage = MemoryStorageRegistry()
    user = UserFactory.build(email="user@relic.local", role=UserRole.ADMIN)
    db_session.add(user)
    db_session.commit()

    body = b"in-memory payload"
    result = object_writes.put_object(
        db_session,
        storage=storage,
        bucket_name="relic",
        key="photos/2026/cat.jpg",
        body=body,
        ingest_meta={"album": "spring"},
        current_user=user,
    )

    digest_hex = hashlib.sha256(body).hexdigest()
    assert result.etag == digest_hex
    assert result.file.name == "cat.jpg"
    assert result.file.meta["album"] == "spring"
    assert storage.storage.get(namespace="blobs", key=result.blob.bucket_key) == body


def test_put_object_deduplicates_identical_bytes(db_session, photos_folder):
    _add_bucket(db_session, name="hot")
    storage = MemoryStorageRegistry()
    user = UserFactory.build(email="user@relic.local", role=UserRole.ADMIN)
    db_session.add(user)
    db_session.commit()

    body = b"shared bytes"
    first = object_writes.put_object(
        db_session,
        storage=storage,
        bucket_name="relic",
        key="photos/a.jpg",
        body=body,
        ingest_meta={},
        current_user=user,
    )
    second = object_writes.put_object(
        db_session,
        storage=storage,
        bucket_name="relic",
        key="photos/b.jpg",
        body=body,
        ingest_meta={},
        current_user=user,
    )

    assert first.blob.id == second.blob.id
    assert second.blob.refcount == 2

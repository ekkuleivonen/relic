"""Tests for metadata extraction helpers."""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from domain.files.meta import build_file_meta
from enums import MetaExtractStatus
from models import AuditEvent, Base, File
from processors.kinds.meta_extract.extractor import (
    detect_mime_type,
    extract_file_metadata,
    is_parquet_file,
)
from tests.factories.models import (
    BlobFactory,
    BucketFactory,
    FolderFactory,
    UserFactory,
)


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


def test_detect_mime_type_recognizes_parquet_extension_when_octet_stream() -> None:
    assert (
        detect_mime_type(prefix=b"", filename="part-00000-c000.snappy.parquet")
        == "application/vnd.apache.parquet"
    )


def test_is_parquet_file_accepts_generic_mime_with_parquet_extension() -> None:
    assert is_parquet_file(
        mime_type="application/octet-stream",
        parser_meta={"extension": "parquet"},
    )


def test_extract_csv_file_accepts_existing_meta_missing_summary(
    db_session, monkeypatch
) -> None:
    user = UserFactory.build()
    bucket = BucketFactory.build()
    folder = FolderFactory.build(name="", parent_id=None)
    db_session.add_all([user, bucket, folder])
    db_session.flush()
    blob = BlobFactory.build(bucket_id=bucket.id, bucket_key="objects/legacy.csv")
    db_session.add(blob)
    db_session.flush()
    existing_meta = build_file_meta(
        file_name="legacy.csv",
        size=13,
        user_meta={},
        mimetype="text/csv",
    )
    existing_meta.pop("summary")
    file = File(
        folder_id=folder.id,
        blob_id=blob.id,
        actor_id=user.id,
        name="legacy.csv",
        meta=existing_meta,
    )
    db_session.add(file)
    db_session.commit()

    csv_bytes = b"a,b\n1,2\n3,4\n"
    monkeypatch.setattr(
        "processors.kinds.meta_extract.extractor.read_blob_prefix", lambda **kwargs: csv_bytes
    )
    monkeypatch.setattr(
        "processors.kinds.meta_extract.extractor.read_blob_bytes_capped",
        lambda **kwargs: csv_bytes,
    )

    result = extract_file_metadata(
        db_session, file_id=file.id, expected_blob_id=file.blob_id
    )

    assert result.status == "completed"
    assert result.file is not None
    assert result.file.meta_extract_status == MetaExtractStatus.COMPLETED
    assert result.file.meta["summary"] == "CSV table with 2 rows and 2 columns"
    assert result.file.meta["kvs"]["row_count"] == 2
    assert db_session.scalars(select(AuditEvent)).all() == []


def test_extract_failure_marks_file_failed_without_audit_event(
    db_session, monkeypatch
) -> None:
    user = UserFactory.build()
    bucket = BucketFactory.build()
    folder = FolderFactory.build(name="", parent_id=None)
    db_session.add_all([user, bucket, folder])
    db_session.flush()
    blob = BlobFactory.build(bucket_id=bucket.id, bucket_key="objects/failing")
    db_session.add(blob)
    db_session.flush()
    file = File(
        folder_id=folder.id,
        blob_id=blob.id,
        actor_id=user.id,
        name="broken.pdf",
        meta={},
    )
    db_session.add(file)
    db_session.commit()

    def fail_read_prefix(**kwargs):
        raise RuntimeError("source object is unreadable")

    monkeypatch.setattr(
        "processors.kinds.meta_extract.extractor.read_blob_prefix", fail_read_prefix
    )

    with pytest.raises(RuntimeError):
        extract_file_metadata(
            db_session, file_id=file.id, expected_blob_id=file.blob_id
        )

    db_session.refresh(file)
    assert file.meta_extract_status == MetaExtractStatus.FAILED
    assert db_session.scalars(select(AuditEvent)).all() == []

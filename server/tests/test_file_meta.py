"""Tests for opaque file meta helpers."""

import json
import uuid

import pytest

from constants import (
    S3_RELIC_BLOB_ID_HEADER,
    S3_RELIC_FILE_ID_HEADER,
    S3_RELIC_FOLDER_ID_HEADER,
    S3_RELIC_META_HEADER,
)
from domain.exceptions import BadRequestError
from domain.files.meta import (
    gateway_user_metadata_headers,
    is_reserved_user_metadata_key,
    normalize_ingest_meta,
    patch_meta,
    validate_user_metadata_ingest,
)


def test_normalize_ingest_meta_copies_user_dict() -> None:
    meta = normalize_ingest_meta({"tags": ["a"], "kvs": {"x": 1}})
    assert meta == {"tags": ["a"], "kvs": {"x": 1}}
    meta["tags"].append("b")
    assert normalize_ingest_meta({"tags": ["a"], "kvs": {"x": 1}})["tags"] == ["a"]


def test_normalize_ingest_meta_empty() -> None:
    assert normalize_ingest_meta(None) == {}
    assert normalize_ingest_meta({}) == {}


def test_patch_meta_deep_merges_nested_objects() -> None:
    existing = {"tags": ["a"], "kvs": {"owner": "team", "version": 1}}
    updated = patch_meta(existing, {"kvs": {"version": 2, "env": "prod"}, "summary": "x"})
    assert updated["tags"] == ["a"]
    assert updated["kvs"] == {"owner": "team", "version": 2, "env": "prod"}
    assert updated["summary"] == "x"


def test_patch_meta_replaces_scalar_and_list_values() -> None:
    existing = {"tags": ["old"], "note": "keep"}
    updated = patch_meta(existing, {"tags": ["new"], "note": "changed"})
    assert updated["tags"] == ["new"]
    assert updated["note"] == "changed"


def test_is_reserved_user_metadata_key() -> None:
    assert is_reserved_user_metadata_key("relic-user")
    assert is_reserved_user_metadata_key("relic-file-id")
    assert is_reserved_user_metadata_key("x-amz-meta-relic-meta")
    assert not is_reserved_user_metadata_key("source")


def test_validate_user_metadata_ingest_rejects_relic_namespace() -> None:
    with pytest.raises(BadRequestError, match="reserved"):
        validate_user_metadata_ingest({"relic-file-id": "fake"})


def test_gateway_user_metadata_headers_exposes_lineage_and_consumer_meta() -> None:
    file_id = uuid.uuid4()
    blob_id = uuid.uuid4()
    folder_id = uuid.uuid4()
    meta = {
        "test_key": 1,
        "tags": ["csv", "finance"],
        "kvs": {"owner": "facet"},
    }

    headers = gateway_user_metadata_headers(
        file_id=file_id,
        blob_id=blob_id,
        folder_id=folder_id,
        meta=meta,
    )

    assert headers[S3_RELIC_FILE_ID_HEADER] == str(file_id)
    assert headers[S3_RELIC_BLOB_ID_HEADER] == str(blob_id)
    assert headers[S3_RELIC_FOLDER_ID_HEADER] == str(folder_id)
    assert json.loads(headers[S3_RELIC_META_HEADER]) == meta
    assert set(headers) == {
        S3_RELIC_FILE_ID_HEADER,
        S3_RELIC_BLOB_ID_HEADER,
        S3_RELIC_FOLDER_ID_HEADER,
        S3_RELIC_META_HEADER,
    }

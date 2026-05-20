"""Tests for opaque file meta helpers."""

import pytest

from domain.exceptions import BadRequestError
from domain.files.meta import normalize_ingest_meta, patch_meta


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

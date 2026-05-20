"""Pure search matching tests."""

from domain.files.search import MetaFilter, SearchQuery, matches_text_filters
from infra.db.models import Blob, File


def test_matches_text_filters_on_flat_meta_and_q():
    blob = Blob(
        storage_backend_id=None,
        bucket_key="k",
        content_hash=b"\x01" * 32,
        size_bytes=1,
        mimetype="application/pdf",
        extension="pdf",
        refcount=1,
    )
    file = File(
        folder_id=None,
        blob_id=None,
        actor_id=None,
        name="report.pdf",
        meta={
            "department": "finance",
            "labels": ["quarterly", "Q1"],
            "row_count": 100,
        },
    )
    file.blob = blob

    query = SearchQuery(q="finance quarterly")
    assert matches_text_filters(file, query) is True

    query = SearchQuery(q="missing-term")
    assert matches_text_filters(file, query) is False


def test_meta_filter_numeric_and_nested_paths():
    file = File(
        folder_id=None,
        blob_id=None,
        actor_id=None,
        name="x",
        meta={"row_count": 150, "audit": {"score": 9}},
    )
    file.blob = Blob(
        storage_backend_id=None,
        bucket_key="k",
        content_hash=b"\x02" * 32,
        size_bytes=1,
        mimetype="application/octet-stream",
        extension="",
        refcount=1,
    )

    assert (
        matches_text_filters(
            file,
            SearchQuery(meta=(MetaFilter.parse("row_count:gte:100"),)),
        )
        is True
    )
    assert (
        matches_text_filters(
            file,
            SearchQuery(meta=(MetaFilter.parse("audit.score:gte:10"),)),
        )
        is False
    )


def test_meta_filter_eq_matches_array_values():
    file = File(
        folder_id=None,
        blob_id=None,
        actor_id=None,
        name="x",
        meta={"tags": ["photo", "large"]},
    )
    file.blob = Blob(
        storage_backend_id=None,
        bucket_key="k",
        content_hash=b"\x03" * 32,
        size_bytes=1,
        mimetype="application/octet-stream",
        extension="",
        refcount=1,
    )

    assert (
        matches_text_filters(
            file,
            SearchQuery(meta=(MetaFilter.parse("tags:eq:photo"),)),
        )
        is True
    )
    assert (
        matches_text_filters(
            file,
            SearchQuery(meta=(MetaFilter.parse("tags:eq:missing"),)),
        )
        is False
    )

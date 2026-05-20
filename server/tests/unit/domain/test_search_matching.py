"""Pure search matching tests."""

from domain.files.search import KvsFilter, SearchQuery, matches_text_filters
from infra.db.models import Blob, File


def test_matches_text_filters_on_tags_and_keywords():
    blob = Blob(
        bucket_id=None,
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
            "tags": ["finance"],
            "keywords": ["quarterly"],
            "summary": "Q1 numbers",
            "kvs": {"row_count": 100},
        },
    )
    file.blob = blob

    query = SearchQuery(tags=("finance",), keywords=("quarterly",), q="Q1")
    assert matches_text_filters(file, query) is True

    query = SearchQuery(tags=("missing",))
    assert matches_text_filters(file, query) is False


def test_kvs_filter_numeric_comparisons():
    file = File(
        folder_id=None,
        blob_id=None,
        actor_id=None,
        name="x",
        meta={"kvs": {"row_count": 150}},
    )
    file.blob = Blob(
        bucket_id=None,
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
            SearchQuery(kvs=(KvsFilter.parse("row_count:gte:100"),)),
        )
        is True
    )
    assert (
        matches_text_filters(
            file,
            SearchQuery(kvs=(KvsFilter.parse("row_count:lt:100"),)),
        )
        is False
    )

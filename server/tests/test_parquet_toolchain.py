"""Tests for processors.kinds.meta_extract.toolchains.parquet."""

import io

import pyarrow as pa
import pyarrow.parquet as pq

from domain.files.meta import FileMeta, build_file_meta
from processors.kinds.meta_extract.toolchains.parquet import empty_parquet_meta, parse, parse_parquet


def _base_meta(file_name: str = "events.parquet") -> dict:
    return build_file_meta(
        file_name=file_name,
        size=10,
        user_meta={},
        mimetype="application/vnd.apache.parquet",
    )


def _validate_with_file(meta: dict) -> None:
    FileMeta.model_validate(meta)


def _parquet_bytes(table: pa.Table, *, compression: str = "snappy") -> bytes:
    buf = io.BytesIO()
    pq.write_table(table, buf, compression=compression)
    return buf.getvalue()


def test_parse_parquet_schema_counts_and_keywords() -> None:
    table = pa.table(
        {
            "user_id": pa.array([1, 2, 3], type=pa.int64()),
            "event_name": ["login", "logout", "login"],
            "created_at": pa.array([1, 2, 3], type=pa.timestamp("s")),
        }
    )
    meta = parse(_parquet_bytes(table), existing_meta=_base_meta())

    assert meta["tags"] == ["data", "dataset", "parquet", "table", "columnar"]
    assert meta["keywords"] == [
        "user_id",
        "event_name",
        "created_at",
        "int64",
        "string",
        "timestamp",
        "snappy",
    ]
    assert meta["kvs"] == {"row_count": 3, "column_count": 3}
    assert meta["summary"] == "parquet table with 3 rows and 3 columns"
    _validate_with_file(meta)


def test_parse_wide_and_tall_parquet() -> None:
    table = pa.table({f"col_{index}": list(range(10_000)) for index in range(50)})
    meta = parse(_parquet_bytes(table), existing_meta=_base_meta("wide.parquet"))

    assert "wide" in meta["tags"]
    assert "tall" in meta["tags"]
    assert meta["kvs"]["row_count"] == 10_000
    assert meta["kvs"]["column_count"] == 50
    _validate_with_file(meta)


def test_parse_partition_hint_from_path() -> None:
    table = pa.table({"amount": [10, 20], "currency": ["usd", "eur"]})
    meta = parse(
        _parquet_bytes(table),
        existing_meta=_base_meta("dt=2026-05-10/part-000.parquet"),
    )

    assert "partitioned" in meta["tags"]
    assert "dt" in meta["keywords"]
    assert "amount" in meta["keywords"]
    _validate_with_file(meta)


def test_parse_parquet_never_raises_and_matches_parser_meta() -> None:
    meta = parse_parquet(content=b"not parquet", existing_meta=_base_meta())

    assert meta == empty_parquet_meta(existing_meta=_base_meta())
    _validate_with_file(meta)

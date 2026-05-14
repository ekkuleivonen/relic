"""Tests for the shared TypeMetaProcessor base.

These exercise the cross-cutting filter logic without spinning up real
parsers: a tiny in-memory ``Processor`` row plus the pre-extracted
``file_info`` mimetype/extension are enough to assert what events an
instance should/shouldn't run on.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from processors.base import BaseProcessor
from processors.type_meta import TypeMetaProcessor


class _ImageMeta(TypeMetaProcessor):
    kind = "image_meta"
    display_name = "Image"
    default_task_queue = "relic:tasks:image_meta"
    default_mimetype_prefixes = ("image/",)
    valid_mimetype_prefixes = ("image/",)
    default_extensions = ()
    valid_extensions = ()
    max_bytes = 1024

    def parse_bytes(
        self, *, content: bytes, file_info: dict[str, Any]
    ) -> dict[str, Any]:
        return {"tags": [], "keywords": [], "summary": None, "kvs": {}}


def test_matches_filters_passes_when_no_filters_set() -> None:
    proc = _ImageMeta()
    instance = MagicMock(mimetype_prefixes=[], extensions=[])
    assert proc.matches_filters(
        mimetype="application/pdf", extension="pdf", processor=instance
    ) is True


def test_matches_filters_blocks_unmatched_mimetype() -> None:
    proc = _ImageMeta()
    instance = MagicMock(mimetype_prefixes=["image/"], extensions=[])
    assert proc.matches_filters(
        mimetype="text/csv", extension="csv", processor=instance
    ) is False


def test_matches_filters_passes_matching_mimetype() -> None:
    proc = _ImageMeta()
    instance = MagicMock(mimetype_prefixes=["image/"], extensions=[])
    assert proc.matches_filters(
        mimetype="image/png", extension="png", processor=instance
    ) is True


def test_matches_filters_blocks_unmatched_extension() -> None:
    proc = _ImageMeta()
    instance = MagicMock(mimetype_prefixes=[], extensions=["jpg", "jpeg"])
    assert proc.matches_filters(
        mimetype="image/png", extension="png", processor=instance
    ) is False


def test_matches_filters_extension_normalizes_leading_dot() -> None:
    proc = _ImageMeta()
    instance = MagicMock(mimetype_prefixes=[], extensions=[".PNG"])
    assert proc.matches_filters(
        mimetype="image/png", extension="png", processor=instance
    ) is True


def test_matches_filters_combines_mimetype_and_extension() -> None:
    proc = _ImageMeta()
    instance = MagicMock(mimetype_prefixes=["image/"], extensions=["png"])
    assert proc.matches_filters(
        mimetype="image/png", extension="png", processor=instance
    ) is True
    assert proc.matches_filters(
        mimetype="image/png", extension="jpg", processor=instance
    ) is False


def test_filter_options_round_trip_back_to_options_for_ui() -> None:
    proc = _ImageMeta()
    options = proc.mimetype_filter_options()
    assert [o.value for o in options] == ["image/"]
    assert [o.default for o in options] == [True]


def test_runtime_valid_event_types_returns_class_var_by_default() -> None:
    proc = _ImageMeta()
    assert proc.runtime_valid_event_types() == ("processor.file_info.completed",)


def test_base_processor_class_var_is_inherited() -> None:
    assert issubclass(_ImageMeta, BaseProcessor)

"""JSON / JSON Lines metadata processor."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

import settings
from processors.base import OrderingSemantics
from processors.kinds.json_meta.parser import parse_json
from processors.type_meta import TypeMetaProcessor


class JsonMetaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JsonMetaProcessor(TypeMetaProcessor):
    kind: ClassVar[str] = "json_meta"
    display_name: ClassVar[str] = "JSON metadata"
    description: ClassVar[str] = (
        "Extracts shape, top-level keys and record counts from JSON or "
        "JSONL files."
    )

    default_task_queue: ClassVar[str] = "relic:tasks:json_meta"
    default_concurrency: ClassVar[int] = 4
    max_concurrency: ClassVar[int] = 16

    default_mimetype_prefixes: ClassVar[tuple[str, ...]] = ("application/json",)
    valid_mimetype_prefixes: ClassVar[tuple[str, ...]] = (
        "application/json",
        "application/x-ndjson",
        "application/jsonl",
        "application/geo+json",
    )
    default_extensions: ClassVar[tuple[str, ...]] = ("json", "jsonl", "geojson")
    valid_extensions: ClassVar[tuple[str, ...]] = (
        "geojson",
        "ipynb",
        "json",
        "jsonl",
    )

    config_model: ClassVar[type[BaseModel]] = JsonMetaConfig
    ordering: ClassVar[OrderingSemantics] = OrderingSemantics.PER_SUBJECT

    max_bytes: ClassVar[int] = settings.JSON_META_MAX_BYTES

    def parse_bytes(
        self, *, content: bytes, file_info: dict[str, Any]
    ) -> dict[str, Any]:
        return parse_json(content=content, file_info=file_info)


__all__ = ["JsonMetaConfig", "JsonMetaProcessor"]

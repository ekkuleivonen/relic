"""Plaintext / source code metadata processor."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

import settings
from processors.base import OrderingSemantics
from processors.kinds.text_meta.parser import parse_text
from processors.type_meta import TypeMetaProcessor


class TextMetaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TextMetaProcessor(TypeMetaProcessor):
    kind: ClassVar[str] = "text_meta"
    display_name: ClassVar[str] = "Text & code metadata"
    description: ClassVar[str] = (
        "Detects encoding, line counts and language signals from plaintext "
        "and source files."
    )

    default_task_queue: ClassVar[str] = "relic:tasks:text_meta"
    default_concurrency: ClassVar[int] = 8
    max_concurrency: ClassVar[int] = 32

    default_mimetype_prefixes: ClassVar[tuple[str, ...]] = ("text/",)
    valid_mimetype_prefixes: ClassVar[tuple[str, ...]] = ("text/",)
    default_extensions: ClassVar[tuple[str, ...]] = ()
    valid_extensions: ClassVar[tuple[str, ...]] = ()

    config_model: ClassVar[type[BaseModel]] = TextMetaConfig
    ordering: ClassVar[OrderingSemantics] = OrderingSemantics.PER_SUBJECT

    max_bytes: ClassVar[int] = settings.TEXT_META_MAX_BYTES

    def parse_bytes(
        self, *, content: bytes, file_info: dict[str, Any]
    ) -> dict[str, Any]:
        return parse_text(content=content, file_info=file_info)


__all__ = ["TextMetaConfig", "TextMetaProcessor"]

"""HTML metadata processor."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

import settings
from processors.base import OrderingSemantics
from processors.kinds.html_meta.parser import parse_html
from processors.type_meta import TypeMetaProcessor


class HtmlMetaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HtmlMetaProcessor(TypeMetaProcessor):
    kind: ClassVar[str] = "html_meta"
    display_name: ClassVar[str] = "HTML metadata"
    description: ClassVar[str] = (
        "Extracts title, headings, canonical domain and other discoverability "
        "signals from HTML pages."
    )

    default_task_queue: ClassVar[str] = "relic:tasks:html_meta"
    default_concurrency: ClassVar[int] = 8
    max_concurrency: ClassVar[int] = 32

    default_mimetype_prefixes: ClassVar[tuple[str, ...]] = ("text/html",)
    valid_mimetype_prefixes: ClassVar[tuple[str, ...]] = (
        "text/html",
        "application/xhtml+xml",
    )
    default_extensions: ClassVar[tuple[str, ...]] = ()
    valid_extensions: ClassVar[tuple[str, ...]] = ("htm", "html", "xhtml")

    config_model: ClassVar[type[BaseModel]] = HtmlMetaConfig
    ordering: ClassVar[OrderingSemantics] = OrderingSemantics.PER_SUBJECT

    max_bytes: ClassVar[int] = settings.HTML_META_MAX_BYTES

    def parse_bytes(
        self, *, content: bytes, file_info: dict[str, Any]
    ) -> dict[str, Any]:
        return parse_html(content=content, file_info=file_info)


__all__ = ["HtmlMetaConfig", "HtmlMetaProcessor"]

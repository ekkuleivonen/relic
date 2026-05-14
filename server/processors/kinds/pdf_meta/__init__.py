"""PDF metadata processor."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

import settings
from processors.base import OrderingSemantics
from processors.kinds.pdf_meta.parser import parse_pdf
from processors.type_meta import TypeMetaProcessor


class PdfMetaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PdfMetaProcessor(TypeMetaProcessor):
    kind: ClassVar[str] = "pdf_meta"
    display_name: ClassVar[str] = "PDF metadata"
    description: ClassVar[str] = (
        "Extracts page count, document properties and discoverability "
        "signals from PDF documents."
    )

    default_task_queue: ClassVar[str] = "relic:tasks:pdf_meta"
    default_concurrency: ClassVar[int] = 4
    max_concurrency: ClassVar[int] = 16

    default_mimetype_prefixes: ClassVar[tuple[str, ...]] = ("application/pdf",)
    valid_mimetype_prefixes: ClassVar[tuple[str, ...]] = ("application/pdf",)

    config_model: ClassVar[type[BaseModel]] = PdfMetaConfig
    ordering: ClassVar[OrderingSemantics] = OrderingSemantics.PER_SUBJECT

    max_bytes: ClassVar[int] = settings.PDF_META_MAX_BYTES

    def parse_bytes(
        self, *, content: bytes, file_info: dict[str, Any]
    ) -> dict[str, Any]:
        return parse_pdf(content=content)


__all__ = ["PdfMetaConfig", "PdfMetaProcessor"]

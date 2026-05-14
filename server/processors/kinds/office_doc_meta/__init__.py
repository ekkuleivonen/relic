"""Office document metadata processor (DOCX/DOC/RTF/ODT)."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

import settings
from processors.base import OrderingSemantics
from processors.kinds.office_doc_meta.parser import parse_office_doc
from processors.type_meta import TypeMetaProcessor


class OfficeDocMetaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OfficeDocMetaProcessor(TypeMetaProcessor):
    kind: ClassVar[str] = "office_doc_meta"
    display_name: ClassVar[str] = "Office document metadata"
    description: ClassVar[str] = (
        "Inspects Word, ODT and RTF documents for properties and "
        "discoverability signals."
    )

    default_task_queue: ClassVar[str] = "relic:tasks:office_doc_meta"
    default_concurrency: ClassVar[int] = 4
    max_concurrency: ClassVar[int] = 16

    default_mimetype_prefixes: ClassVar[tuple[str, ...]] = (
        "application/msword",
        "application/rtf",
        "application/vnd.oasis.opendocument.text",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/rtf",
    )
    valid_mimetype_prefixes: ClassVar[tuple[str, ...]] = (
        "application/msword",
        "application/rtf",
        "application/vnd.oasis.opendocument.text",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/rtf",
    )
    default_extensions: ClassVar[tuple[str, ...]] = ("doc", "docx", "odt", "rtf")
    valid_extensions: ClassVar[tuple[str, ...]] = ("doc", "docx", "odt", "rtf")

    config_model: ClassVar[type[BaseModel]] = OfficeDocMetaConfig
    ordering: ClassVar[OrderingSemantics] = OrderingSemantics.PER_SUBJECT

    max_bytes: ClassVar[int] = settings.OFFICE_DOC_META_MAX_BYTES

    def parse_bytes(
        self, *, content: bytes, file_info: dict[str, Any]
    ) -> dict[str, Any]:
        return parse_office_doc(content=content, file_info=file_info)


__all__ = ["OfficeDocMetaConfig", "OfficeDocMetaProcessor"]

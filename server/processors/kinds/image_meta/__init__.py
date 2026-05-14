"""Image metadata processor (PNG/JPEG/HEIC/...).

Reads up to ``IMAGE_META_MAX_BYTES`` and writes ``meta.sections.image_meta``.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

import settings
from processors.base import OrderingSemantics
from processors.kinds.image_meta.parser import parse_image
from processors.type_meta import TypeMetaProcessor


class ImageMetaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ImageMetaProcessor(TypeMetaProcessor):
    kind: ClassVar[str] = "image_meta"
    display_name: ClassVar[str] = "Image metadata"
    description: ClassVar[str] = (
        "Extracts dimensions, format and EXIF facts from image files."
    )

    default_task_queue: ClassVar[str] = "relic:tasks:image_meta"
    default_concurrency: ClassVar[int] = 8
    max_concurrency: ClassVar[int] = 32

    default_mimetype_prefixes: ClassVar[tuple[str, ...]] = ("image/",)
    valid_mimetype_prefixes: ClassVar[tuple[str, ...]] = ("image/",)

    config_model: ClassVar[type[BaseModel]] = ImageMetaConfig
    ordering: ClassVar[OrderingSemantics] = OrderingSemantics.PER_SUBJECT

    max_bytes: ClassVar[int] = settings.IMAGE_META_MAX_BYTES

    def parse_bytes(
        self, *, content: bytes, file_info: dict[str, Any]
    ) -> dict[str, Any]:
        return parse_image(content=content)


__all__ = ["ImageMetaConfig", "ImageMetaProcessor"]

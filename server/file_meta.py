"""Canonical shapes for ``File.ingest_meta`` and ``File.parser_meta``."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


class IngestMeta(BaseModel):
    """S3 user metadata (string tags) plus Relic's ``original_filename``."""

    model_config = ConfigDict(extra="allow")
    original_filename: str

    @model_validator(mode="after")
    def _extras_are_strings(self) -> IngestMeta:
        if not self.__pydantic_extra__:
            return self
        for key, value in self.__pydantic_extra__.items():
            if not isinstance(value, str):
                raise ValueError(
                    f"Ingest meta values must be strings, got {type(value).__name__} for {key!r}"
                )
        return self


class ParserFileSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_filename: str
    mime_type: str
    size: int
    extension: str


class ImageParserSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width: int | None
    height: int | None
    megapixels: float | None
    aspect_ratio: str | None
    format: str | None
    color_mode: str | None
    has_alpha: bool | None
    is_animated: bool | None
    is_grayscale: bool | None
    orientation: int | None
    camera_make: str | None
    camera_model: str | None
    datetime_original: str | None
    gps_latitude: float | None
    gps_longitude: float | None


class CsvParserSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_count: int | None
    column_count: int | None
    columns: list[str] | None
    column_types: dict[str, str] | None
    delimiter: str | None
    quote_char: str | None
    has_header: bool | None
    encoding: str | None
    line_terminator: str | None
    skipped_prefix_rows: int | None
    empty_cells_pct: float | None


class ParserMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file: ParserFileSection
    image: ImageParserSection | None = None
    csv: CsvParserSection | None = None


def normalize_ingest_meta(stored: dict[str, Any]) -> dict[str, Any]:
    return IngestMeta.model_validate(stored).model_dump(mode="json")


def dump_ingest_meta(*, file_name: str, ingest_meta: dict[str, Any]) -> dict[str, Any]:
    return IngestMeta.model_validate(
        {"original_filename": file_name, **ingest_meta}
    ).model_dump(mode="json")


def validate_parser_meta_dict(parser_meta: dict[str, Any]) -> ParserMeta:
    return ParserMeta.model_validate(parser_meta)

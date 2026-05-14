"""Auto-discovered registry for processor kinds."""

import importlib
import inspect
import pkgutil
from collections.abc import Iterable

from pydantic import ValidationError

from domain.exceptions import BadRequestError
from processors.base import BaseProcessor
from utils.logging import get_logger

log = get_logger(__name__)

_PROCESSORS: dict[str, BaseProcessor] = {}


def register_processor(processor_cls: type[BaseProcessor]) -> BaseProcessor:
    if inspect.isabstract(processor_cls):
        raise ValueError(f"{processor_cls.__name__} cannot be abstract")
    processor_cls.validate_definition()
    processor = processor_cls()
    if processor.kind in _PROCESSORS:
        log.debug("processor_kind_re_registered", kind=processor.kind)
    _PROCESSORS[processor.kind] = processor
    return processor


def get_processor_kind(kind: str) -> BaseProcessor:
    processor = _PROCESSORS.get(kind)
    if processor is None:
        raise BadRequestError(f"Unknown processor kind: {kind!r}")
    return processor


def list_processor_definitions() -> list[BaseProcessor]:
    return [_PROCESSORS[kind] for kind in sorted(_PROCESSORS.keys())]


def validate_subscribed_event_types(
    *, kind: str, event_types: Iterable[str]
) -> list[str]:
    processor = get_processor_kind(kind)
    valid = set(processor.runtime_valid_event_types())
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in event_types:
        value = (raw or "").strip()
        if not value:
            continue
        if value in seen:
            continue
        if value not in valid:
            raise BadRequestError(
                f"event_type {value!r} is not valid for kind {kind!r}; "
                f"allowed: {sorted(valid)}"
            )
        seen.add(value)
        cleaned.append(value)
    if not cleaned:
        raise BadRequestError("subscribed_event_types must include at least one type")
    return cleaned


def validate_mimetype_prefixes(
    *, kind: str, prefixes: Iterable[str] | None
) -> list[str]:
    """Trim, dedupe, and normalize mimetype-prefix filters."""
    if prefixes is None:
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in prefixes:
        if not isinstance(raw, str):
            raise BadRequestError(
                f"mimetype_prefixes for kind {kind!r} must be strings"
            )
        value = raw.strip().lower()
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        cleaned.append(value)
    return cleaned


def validate_extensions(
    *, kind: str, extensions: Iterable[str] | None
) -> list[str]:
    """Trim, dedupe, and normalize extension filters (no leading dot)."""
    if extensions is None:
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in extensions:
        if not isinstance(raw, str):
            raise BadRequestError(
                f"extensions for kind {kind!r} must be strings"
            )
        value = raw.strip().lower().lstrip(".")
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        cleaned.append(value)
    return cleaned


def validate_config(*, kind: str, config: dict | None) -> dict:
    processor = get_processor_kind(kind)
    try:
        parsed = processor.parse_config(config)
    except ValidationError as exc:
        raise BadRequestError(f"config invalid for kind {kind!r}: {exc}") from exc
    return parsed.model_dump(mode="json")


def autodiscover_processors() -> None:
    """Import every first-party processor kind module and register its classes."""
    import processors.kinds as processor_kinds

    for module in pkgutil.iter_modules(processor_kinds.__path__):
        imported = importlib.import_module(f"{processor_kinds.__name__}.{module.name}")
        for _, obj in inspect.getmembers(imported, inspect.isclass):
            if (
                issubclass(obj, BaseProcessor)
                and obj is not BaseProcessor
                and not inspect.isabstract(obj)
                and obj.__module__ == imported.__name__
            ):
                register_processor(obj)


def init_builtin_processors() -> None:
    """Idempotently register first-party processor kinds."""
    autodiscover_processors()


__all__ = [
    "autodiscover_processors",
    "get_processor_kind",
    "init_builtin_processors",
    "list_processor_definitions",
    "register_processor",
    "validate_config",
    "validate_extensions",
    "validate_mimetype_prefixes",
    "validate_subscribed_event_types",
]

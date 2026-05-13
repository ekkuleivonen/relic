"""Substrate registry for warm processors.

Maps a processor `kind` (the discriminator persisted on each `Processor` row)
to the python callable that knows how to act on a `FileEvent`.

Substrate handlers are pure functions over a session and the inbound event.
The worker is responsible for the cursor commit and the `processor.<kind>.*`
outcome event — handlers must not write to those tables themselves.
"""

import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy.orm import Session

from domain.exceptions import BadRequestError
from models import FileEvent
from utils.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class ProcessorContext:
    """What the worker hands the substrate handler."""

    processor_id: uuid.UUID
    processor_name: str
    config: dict
    file_event: FileEvent


SubstrateHandler = Callable[[Session, ProcessorContext], None]


class EmptyProcessorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class Substrate:
    kind: str
    handler: SubstrateHandler
    default_subscribed_event_types: tuple[str, ...]
    valid_event_types: tuple[str, ...]
    config_model: type[BaseModel]


_SUBSTRATES: dict[str, Substrate] = {}


def register(
    *,
    kind: str,
    handler: SubstrateHandler,
    default_subscribed_event_types: Iterable[str],
    valid_event_types: Iterable[str],
    config_model: type[BaseModel] = EmptyProcessorConfig,
) -> Substrate:
    if kind in _SUBSTRATES:
        log.debug("substrate_re_registered", kind=kind)
    substrate = Substrate(
        kind=kind,
        handler=handler,
        default_subscribed_event_types=tuple(default_subscribed_event_types),
        valid_event_types=tuple(valid_event_types),
        config_model=config_model,
    )
    _SUBSTRATES[kind] = substrate
    return substrate


def get_substrate(kind: str) -> Substrate:
    substrate = _SUBSTRATES.get(kind)
    if substrate is None:
        raise BadRequestError(f"Unknown processor kind: {kind!r}")
    return substrate


def list_substrate_kinds() -> list[str]:
    return sorted(_SUBSTRATES.keys())


def validate_subscribed_event_types(
    *, kind: str, event_types: Iterable[str]
) -> list[str]:
    substrate = get_substrate(kind)
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in event_types:
        value = (raw or "").strip()
        if not value:
            continue
        if value in seen:
            continue
        if value not in substrate.valid_event_types:
            raise BadRequestError(
                f"event_type {value!r} is not valid for kind {kind!r}; "
                f"allowed: {sorted(substrate.valid_event_types)}"
            )
        seen.add(value)
        cleaned.append(value)
    if not cleaned:
        raise BadRequestError("subscribed_event_types must include at least one type")
    return cleaned


def validate_config(*, kind: str, config: dict | None) -> dict:
    substrate = get_substrate(kind)
    try:
        parsed = substrate.config_model.model_validate(config or {})
    except ValidationError as exc:
        raise BadRequestError(f"config invalid for kind {kind!r}: {exc}") from exc
    return parsed.model_dump(mode="json")


def init_builtin_substrates() -> None:
    """Idempotently register first-party substrates.

    Called from API and worker startup. Importing the substrate module triggers
    its `register(...)` call.
    """
    from processors.meta_extract import register_substrate as register_meta_extract

    register_meta_extract()

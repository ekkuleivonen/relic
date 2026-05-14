"""Developer-facing contract for first-party and admin-managed processors."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from models import FileEvent, Processor
from utils.logging import get_logger

log = get_logger(__name__)


class DeliverySemantics(StrEnum):
    AT_LEAST_ONCE = "at_least_once"


class OrderingSemantics(StrEnum):
    NONE = "none"
    PER_SUBJECT = "per_subject"
    GLOBAL = "global"


class IdempotencySemantics(StrEnum):
    REQUIRED = "required"


class EmptyProcessorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EventTypeOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    label: str
    default: bool = False


class MimetypeFilterOption(BaseModel):
    """One discoverable choice for the mimetype-prefix subscription filter."""

    model_config = ConfigDict(extra="forbid")

    value: str
    label: str
    default: bool = False


class ExtensionFilterOption(BaseModel):
    """One discoverable choice for the extension subscription filter."""

    model_config = ConfigDict(extra="forbid")

    value: str
    label: str
    default: bool = False


class ProcessorTask(BaseModel):
    """Portable work descriptor emitted from a durable file event.

    The current runtime still executes tasks through the existing warm-path
    cursor worker, but this task shape is the contract Redis Streams workers
    will consume.
    """

    model_config = ConfigDict(extra="forbid")

    processor_id: uuid.UUID
    processor_name: str
    processor_kind: str
    source_event_id: uuid.UUID
    source_event_type: str
    subject_type: Literal["file", "blob", "folder", "event", "external"]
    subject_id: uuid.UUID | str
    input_version: str | int | None = None
    dedupe_key: str = Field(min_length=1)
    queue_name: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class ProcessorResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["succeeded", "skipped", "stale"] = "succeeded"
    message: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def succeeded(cls, **details: Any) -> "ProcessorResult":
        return cls(status="succeeded", details=details)

    @classmethod
    def skipped(cls, message: str, **details: Any) -> "ProcessorResult":
        return cls(status="skipped", message=message, details=details)

    @classmethod
    def stale(cls, message: str, **details: Any) -> "ProcessorResult":
        return cls(status="stale", message=message, details=details)


class EnqueueContext(BaseModel):
    """Context available while turning a file event into a processor task."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    db: Session
    processor: Processor
    event: FileEvent
    config: BaseModel


class RunContext(BaseModel):
    """Context available while executing one processor task."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    db: Session
    processor: Processor
    event: FileEvent
    task: ProcessorTask
    config: BaseModel


class BaseProcessor(ABC):
    """Blueprint every processor kind should follow.

    Python classes declare capabilities and defaults. The `processors` table
    stores operator-managed instances: enabled state, subscriptions, scopes,
    and config.
    """

    kind: ClassVar[str]
    display_name: ClassVar[str]
    description: ClassVar[str] = ""

    default_task_queue: ClassVar[str]
    default_concurrency: ClassVar[int] = 1
    max_concurrency: ClassVar[int] = 1

    default_subscribed_event_types: ClassVar[tuple[str, ...]]
    valid_event_types: ClassVar[tuple[str, ...]]

    # Per-kind defaults + allowed values for the mimetype-prefix and
    # extension subscription filters. ``valid_*`` is informational and
    # surfaced to the UI; instances may use other values via the API.
    default_mimetype_prefixes: ClassVar[tuple[str, ...]] = ()
    valid_mimetype_prefixes: ClassVar[tuple[str, ...]] = ()
    default_extensions: ClassVar[tuple[str, ...]] = ()
    valid_extensions: ClassVar[tuple[str, ...]] = ()

    config_model: ClassVar[type[BaseModel]] = EmptyProcessorConfig

    delivery: ClassVar[DeliverySemantics] = DeliverySemantics.AT_LEAST_ONCE
    ordering: ClassVar[OrderingSemantics] = OrderingSemantics.PER_SUBJECT
    idempotency: ClassVar[IdempotencySemantics] = IdempotencySemantics.REQUIRED

    @classmethod
    def validate_definition(cls) -> None:
        required_strings = {
            "kind": getattr(cls, "kind", ""),
            "display_name": getattr(cls, "display_name", ""),
            "default_task_queue": getattr(cls, "default_task_queue", ""),
        }
        for field, value in required_strings.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{cls.__name__}.{field} must be a non-empty string")
        if cls.default_concurrency < 1:
            raise ValueError(f"{cls.__name__}.default_concurrency must be >= 1")
        if cls.max_concurrency < cls.default_concurrency:
            raise ValueError(
                f"{cls.__name__}.max_concurrency must be >= default_concurrency"
            )
        if not cls.default_subscribed_event_types:
            raise ValueError(
                f"{cls.__name__}.default_subscribed_event_types cannot be empty"
            )
        invalid_defaults = set(cls.default_subscribed_event_types) - set(
            cls.valid_event_types
        )
        if invalid_defaults:
            raise ValueError(
                f"{cls.__name__} default subscriptions are not valid: "
                f"{sorted(invalid_defaults)}"
            )
        invalid_mimetype_defaults = set(cls.default_mimetype_prefixes) - set(
            cls.valid_mimetype_prefixes
        )
        if invalid_mimetype_defaults:
            raise ValueError(
                f"{cls.__name__} default_mimetype_prefixes contain unknown values: "
                f"{sorted(invalid_mimetype_defaults)}"
            )
        invalid_extension_defaults = set(cls.default_extensions) - set(
            cls.valid_extensions
        )
        if invalid_extension_defaults:
            raise ValueError(
                f"{cls.__name__} default_extensions contain unknown values: "
                f"{sorted(invalid_extension_defaults)}"
            )

    def parse_config(self, raw_config: dict | None) -> BaseModel:
        return self.config_model.model_validate(raw_config or {})

    def public_config(self, raw_config: dict | None) -> dict[str, Any]:
        return self.parse_config(raw_config).model_dump(mode="json")

    def config_schema(self) -> dict[str, Any]:
        return self.config_model.model_json_schema()

    def runtime_valid_event_types(self) -> tuple[str, ...]:
        """Resolve the valid event-type list at runtime.

        Defaults to the ``valid_event_types`` ClassVar, which most processors
        declare statically. Processor kinds whose deliverable events depend on
        which other kinds are registered (e.g. ``webhook_event_dispatch``)
        override this hook so the API exposes an accurate list.
        """
        return tuple(self.valid_event_types)

    def event_type_options(self) -> list[EventTypeOption]:
        defaults = set(self.default_subscribed_event_types)
        return [
            EventTypeOption(
                value=event_type,
                label=event_type,
                default=event_type in defaults,
            )
            for event_type in self.runtime_valid_event_types()
        ]

    def mimetype_filter_options(self) -> list[MimetypeFilterOption]:
        defaults = set(self.default_mimetype_prefixes)
        return [
            MimetypeFilterOption(
                value=prefix,
                label=prefix,
                default=prefix in defaults,
            )
            for prefix in self.valid_mimetype_prefixes
        ]

    def extension_filter_options(self) -> list[ExtensionFilterOption]:
        defaults = set(self.default_extensions)
        return [
            ExtensionFilterOption(
                value=extension,
                label=extension,
                default=extension in defaults,
            )
            for extension in self.valid_extensions
        ]

    def should_enqueue(self, ctx: EnqueueContext) -> bool:
        return True

    def matches_filters(
        self,
        *,
        mimetype: str | None,
        extension: str | None,
        processor: Processor,
    ) -> bool:
        """Apply the processor instance's mimetype/extension filters.

        Returns True when the file's observed mimetype/extension match every
        configured filter, or when no filters are set. Empty filters mean
        "no filter" (every event passes through).
        """
        prefixes: list[str] = list(processor.mimetype_prefixes or [])
        if prefixes:
            normalized_mimetype = (mimetype or "").lower()
            if not any(
                normalized_mimetype.startswith(prefix.lower()) for prefix in prefixes
            ):
                return False

        extensions: list[str] = list(processor.extensions or [])
        if extensions:
            normalized_extension = (extension or "").lower().lstrip(".")
            if normalized_extension not in {ext.lower().lstrip(".") for ext in extensions}:
                return False
        return True

    @abstractmethod
    def build_task(self, ctx: EnqueueContext) -> ProcessorTask:
        """Build a durable, JSON-safe task description from a file event."""

    def route_task_queue(self, task: ProcessorTask, ctx: EnqueueContext) -> str:
        return self.default_task_queue

    @abstractmethod
    def handle(self, ctx: RunContext) -> ProcessorResult:
        """Execute one task. Handlers must be idempotent over `task.dedupe_key`."""

    def execute_event(self, db: Session, processor: Processor, event: FileEvent) -> None:
        """Execute one file event through this processor kind."""
        config = self.parse_config(processor.config)
        enqueue_context = EnqueueContext(
            db=db,
            processor=processor,
            event=event,
            config=config,
        )
        if not self.should_enqueue(enqueue_context):
            log.info(
                "processor_event_skipped",
                processor_id=str(processor.id),
                processor_name=processor.name,
                kind=self.kind,
                event_id=str(event.id),
                event_type=event.event_type,
            )
            return

        task = self.build_task(enqueue_context)
        routed_task = task.model_copy(
            update={"queue_name": self.route_task_queue(task, enqueue_context)}
        )
        result = self.handle(
            RunContext(
                db=db,
                processor=processor,
                event=event,
                task=routed_task,
                config=config,
            )
        )
        if result.status != "succeeded":
            log.info(
                "processor_task_finished_non_success",
                processor_id=str(processor.id),
                processor_name=processor.name,
                kind=self.kind,
                event_id=str(event.id),
                task_dedupe_key=routed_task.dedupe_key,
                status=result.status,
                message=result.message,
            )

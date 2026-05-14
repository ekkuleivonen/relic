"""Processor kind that delivers selected file events to an HTTP webhook."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator

from processors.base import (
    BaseProcessor,
    EnqueueContext,
    OrderingSemantics,
    ProcessorResult,
    ProcessorTask,
    RunContext,
)
from processors.kinds.webhook_event_dispatch.client import (
    build_webhook_body,
    clean_headers,
    post_webhook,
    sign_webhook_body,
)

WEBHOOK_DELIVERABLE_EVENT_TYPES = (
    "file.created",
    "file.updated",
    "file.copied",
    "file.renamed",
    "file.moved",
    "file.deleted",
    "folder.created",
    "folder.updated",
    "folder.moved",
    "folder.deleted",
    "processor.meta_extract.completed",
    "processor.meta_extract.failed",
)


class WebhookEventDispatchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: AnyHttpUrl = Field(
        description="HTTPS endpoint that receives signed Relic event payloads."
    )
    secret: str = Field(
        min_length=16,
        description="Shared signing secret used for X-Relic-Signature.",
        json_schema_extra={"format": "password", "writeOnly": True},
    )
    timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="Additional static headers sent with every webhook request.",
    )

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, value: dict[str, str]) -> dict[str, str]:
        return clean_headers(value)


class WebhookEventDispatchProcessor(BaseProcessor):
    kind: ClassVar[str] = "webhook_event_dispatch"
    display_name: ClassVar[str] = "Webhook event dispatch"
    description: ClassVar[str] = "Delivers selected file events to an HTTP webhook."

    default_task_queue: ClassVar[str] = "relic:tasks:webhook_event_dispatch"
    default_concurrency: ClassVar[int] = 16
    max_concurrency: ClassVar[int] = 64

    default_subscribed_event_types: ClassVar[tuple[str, ...]] = (
        "file.created",
        "file.updated",
        "file.deleted",
        "processor.meta_extract.completed",
        "processor.meta_extract.failed",
    )
    valid_event_types: ClassVar[tuple[str, ...]] = WEBHOOK_DELIVERABLE_EVENT_TYPES
    config_model: ClassVar[type[BaseModel]] = WebhookEventDispatchConfig
    ordering: ClassVar[OrderingSemantics] = OrderingSemantics.NONE

    def public_config(self, raw_config: dict | None) -> dict[str, Any]:
        config = WebhookEventDispatchConfig.model_validate(raw_config or {})
        data = config.model_dump(mode="json")
        data["secret"] = "********"
        return data

    def build_task(self, ctx: EnqueueContext) -> ProcessorTask:
        event = ctx.event
        return ProcessorTask(
            processor_id=ctx.processor.id,
            processor_name=ctx.processor.name,
            processor_kind=self.kind,
            source_event_id=event.id,
            source_event_type=event.event_type,
            subject_type="event",
            subject_id=event.id,
            input_version=event.offset,
            dedupe_key=f"{self.kind}:{ctx.processor.id}:event:{event.id}",
            queue_name=self.default_task_queue,
            payload={
                "event": {
                    "id": str(event.id),
                    "offset": event.offset,
                    "created_at": event.created_at.isoformat()
                    if event.created_at
                    else None,
                    "schema_version": event.schema_version,
                    "event_type": event.event_type,
                    "status": event.status,
                    "actor_id": str(event.actor_id) if event.actor_id else None,
                    "request_id": event.request_id,
                    "idempotency_key": event.idempotency_key,
                    "file_id": str(event.file_id) if event.file_id else None,
                    "folder_id": str(event.folder_id) if event.folder_id else None,
                    "payload": dict(event.payload or {}),
                }
            },
        )

    def handle(self, ctx: RunContext) -> ProcessorResult:
        config = WebhookEventDispatchConfig.model_validate(ctx.config)
        body = build_webhook_body(ctx.task)
        status_code = post_webhook(
            url=str(config.url),
            body=body,
            headers={
                **config.headers,
                "Content-Type": "application/json",
                "X-Relic-Event-Id": str(ctx.task.source_event_id),
                "X-Relic-Event-Type": ctx.task.source_event_type,
                "X-Relic-Processor-Id": str(ctx.task.processor_id),
                "X-Relic-Processor-Kind": self.kind,
                "X-Relic-Signature": sign_webhook_body(
                    body=body,
                    secret=config.secret,
                ),
                "Idempotency-Key": ctx.task.dedupe_key,
            },
            timeout_seconds=config.timeout_seconds,
        )
        return ProcessorResult.succeeded(
            event_id=str(ctx.task.source_event_id),
            endpoint=str(config.url),
            status_code=status_code,
        )

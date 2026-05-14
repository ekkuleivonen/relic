"""Tests for the webhook event dispatch processor kind."""

import json
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models import Base, Processor
from processors.base import EnqueueContext, RunContext
from processors.kinds.webhook_event_dispatch import (
    WebhookEventDispatchConfig,
    WebhookEventDispatchProcessor,
)
from processors.kinds.webhook_event_dispatch.client import (
    build_webhook_body,
    sign_webhook_body,
)
from services.file_events import create_file_event
from tests.factories.models import ProcessorFactory


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with SessionLocal() as session:
        yield session


def test_config_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        WebhookEventDispatchConfig.model_validate(
            {
                "url": "https://example.com/relic",
                "secret": "a" * 32,
                "unexpected": True,
            }
        )


def test_build_task_uses_processor_and_event_for_idempotency(db_session) -> None:
    processor = ProcessorFactory.build(
        name="webhook:acme",
        kind="webhook_event_dispatch",
        config={"url": "https://example.com/relic", "secret": "a" * 32},
    )
    db_session.add(processor)
    db_session.flush()
    event = create_file_event(
        db_session,
        event_type="file.created",
        file_id=uuid.uuid4(),
        payload={"name": "report.pdf"},
    )

    webhook = WebhookEventDispatchProcessor()
    task = webhook.build_task(
        EnqueueContext(
            db=db_session,
            processor=processor,
            event=event,
            config=webhook.parse_config(processor.config),
        )
    )

    assert task.subject_type == "event"
    assert task.subject_id == event.id
    assert task.input_version == event.offset
    assert task.dedupe_key == f"webhook_event_dispatch:{processor.id}:event:{event.id}"
    assert task.payload["event"]["event_type"] == "file.created"
    assert task.payload["event"]["payload"] == {"name": "report.pdf"}


def test_webhook_signature_is_stable_and_prefixed() -> None:
    body = b'{"event":{"id":"evt_1"}}'

    signature = sign_webhook_body(body=body, secret="s" * 32)

    assert signature.startswith("sha256=")
    assert signature == sign_webhook_body(body=body, secret="s" * 32)
    assert signature != sign_webhook_body(body=body, secret="x" * 32)


def test_build_webhook_body_is_canonical_json(db_session) -> None:
    processor = ProcessorFactory.build(
        name="webhook:acme",
        kind="webhook_event_dispatch",
        config={"url": "https://example.com/relic", "secret": "a" * 32},
    )
    db_session.add(processor)
    db_session.flush()
    event = create_file_event(
        db_session,
        event_type="processor.file_info.completed",
        file_id=uuid.uuid4(),
        payload={"kind": "file_info", "duration_ms": 7},
    )
    webhook = WebhookEventDispatchProcessor()
    task = webhook.build_task(
        EnqueueContext(
            db=db_session,
            processor=processor,
            event=event,
            config=webhook.parse_config(processor.config),
        )
    )

    body = build_webhook_body(task)

    decoded = json.loads(body)
    assert decoded["event"]["id"] == str(event.id)
    assert decoded["event"]["offset"] == event.offset
    assert decoded["event"]["payload"] == {"duration_ms": 7, "kind": "file_info"}
    assert body == build_webhook_body(task)


def test_handle_posts_signed_event(monkeypatch, db_session) -> None:
    captured: dict[str, object] = {}

    def fake_post_webhook(**kwargs):
        captured.update(kwargs)
        return 202

    monkeypatch.setattr(
        "processors.kinds.webhook_event_dispatch.post_webhook", fake_post_webhook
    )
    processor = ProcessorFactory.build(
        name="webhook:acme",
        kind="webhook_event_dispatch",
        config={
            "url": "https://example.com/relic",
            "secret": "a" * 32,
            "headers": {"X-Custom": "yes"},
        },
    )
    db_session.add(processor)
    db_session.flush()
    event = create_file_event(
        db_session,
        event_type="file.deleted",
        file_id=uuid.uuid4(),
        payload={"reason": "user_request"},
    )
    webhook = WebhookEventDispatchProcessor()
    config = webhook.parse_config(processor.config)
    task = webhook.build_task(
        EnqueueContext(
            db=db_session,
            processor=processor,
            event=event,
            config=config,
        )
    )

    result = webhook.handle(
        RunContext(
            db=db_session,
            processor=processor,
            event=event,
            task=task,
            config=config,
        )
    )

    assert result.status == "succeeded"
    assert captured["url"] == "https://example.com/relic"
    assert captured["timeout_seconds"] == 5.0
    assert captured["headers"]["X-Custom"] == "yes"
    assert captured["headers"]["X-Relic-Event-Id"] == str(event.id)
    assert captured["headers"]["Idempotency-Key"] == task.dedupe_key
    assert captured["headers"]["X-Relic-Signature"].startswith("sha256=")

"""HTTP delivery helpers for webhook event dispatch."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from processors.base import ProcessorTask


class WebhookDeliveryError(RuntimeError):
    """Raised when a webhook endpoint rejects or cannot receive an event."""


def build_webhook_body(task: ProcessorTask) -> bytes:
    """Serialize task payload into stable JSON for signing and delivery."""
    body = {
        "processor": {
            "id": str(task.processor_id),
            "name": task.processor_name,
            "kind": task.processor_kind,
        },
        "task": {
            "dedupe_key": task.dedupe_key,
            "subject_type": task.subject_type,
            "subject_id": str(task.subject_id),
            "input_version": task.input_version,
        },
        **task.payload,
    }
    return json.dumps(
        body,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sign_webhook_body(*, body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def post_webhook(
    *,
    url: str,
    body: bytes,
    headers: dict[str, str],
    timeout_seconds: float,
) -> int:
    request = Request(
        url,
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            status_code = int(response.status)
    except HTTPError as exc:
        raise WebhookDeliveryError(f"Webhook returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise WebhookDeliveryError(f"Webhook delivery failed: {exc}") from exc
    if status_code < 200 or status_code >= 300:
        raise WebhookDeliveryError(f"Webhook returned HTTP {status_code}")
    return status_code


def clean_headers(headers: dict[str, Any]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for raw_key, raw_value in headers.items():
        key = str(raw_key).strip()
        if not key:
            continue
        cleaned[key] = str(raw_value)
    return cleaned

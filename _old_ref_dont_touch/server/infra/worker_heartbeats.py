"""Redis-backed liveness heartbeats for background workers."""

from __future__ import annotations

import time
from typing import Any

import settings as S
from enums import HealthStatus
from infra.redis.client import get_redis_client

_MAINTENANCE_HEARTBEAT_KEY = "heartbeat:maintenance"


def touch_maintenance_heartbeat() -> None:
    client = get_redis_client()
    client.set(
        client.key(_MAINTENANCE_HEARTBEAT_KEY),
        str(time.time()).encode(),
        ex=S.MAINTENANCE_HEARTBEAT_TTL_SECONDS,
    )


def maintenance_heartbeat_status() -> dict[str, Any]:
    client = get_redis_client()
    raw = client.get(client.key(_MAINTENANCE_HEARTBEAT_KEY))
    if raw is None:
        status = (
            HealthStatus.FAILED.value
            if S.MAINTENANCE_HEARTBEAT_REQUIRED
            else HealthStatus.OK.value
        )
        return {
            "status": status,
            "required": S.MAINTENANCE_HEARTBEAT_REQUIRED,
            "last_seen_seconds_ago": None,
        }

    try:
        last_seen = float(raw.decode())
    except ValueError:
        return {
            "status": HealthStatus.FAILED.value,
            "required": S.MAINTENANCE_HEARTBEAT_REQUIRED,
            "last_seen_seconds_ago": None,
            "error": "invalid heartbeat timestamp",
        }

    age = max(0.0, time.time() - last_seen)
    status = (
        HealthStatus.FAILED.value
        if age > S.MAINTENANCE_HEARTBEAT_STALE_SECONDS
        else HealthStatus.OK.value
    )
    return {
        "status": status,
        "required": S.MAINTENANCE_HEARTBEAT_REQUIRED,
        "last_seen_seconds_ago": age,
        "stale_after_seconds": S.MAINTENANCE_HEARTBEAT_STALE_SECONDS,
    }

"""Stable cache scope identifiers shared across API processes."""

from __future__ import annotations

import hashlib
from functools import lru_cache

from infra.db.engine import get_database_url


@lru_cache
def deployment_scope() -> str:
    digest = hashlib.sha256(get_database_url().encode("utf-8")).hexdigest()
    return digest[:16]

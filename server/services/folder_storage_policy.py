"""Resolve per-folder storage overrides vs inherited defaults from ancestors."""

import uuid

from enums import BucketTier
from models import Folder
from sqlalchemy.orm import Session


def effective_min_tier(db: Session, folder: Folder) -> int:
    """
    First explicit ``min_tier`` on this folder or a nearest ancestor, otherwise HOT.

    ``min_tier`` NULL means inherit. The root folder should keep an explicit tier;
    if the chain is empty of values, HOT is used.
    """
    current: Folder | None = folder
    visited: set[uuid.UUID] = set()
    while current is not None and current.id not in visited:
        visited.add(current.id)
        if current.min_tier is not None:
            return current.min_tier
        if current.parent_id is None:
            return int(BucketTier.HOT)
        current = db.get(Folder, current.parent_id)
    return int(BucketTier.HOT)


def effective_cooldown_days(db: Session, folder: Folder) -> int | None:
    """First explicit ``cooldown_days`` on this folder or a nearest ancestor, else None."""
    current: Folder | None = folder
    visited: set[uuid.UUID] = set()
    while current is not None and current.id not in visited:
        visited.add(current.id)
        if current.cooldown_days is not None:
            return current.cooldown_days
        if current.parent_id is None:
            return None
        current = db.get(Folder, current.parent_id)
    return None

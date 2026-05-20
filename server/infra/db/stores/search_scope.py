"""Folder scope resolution for file search."""

from __future__ import annotations

import uuid

from domain.files.search import SearchQuery
from infra.db.models import User
from infra.db.stores import filesystem
from infra.db.stores import folder_access
from sqlalchemy.orm import Session


def scope_folder_ids(db: Session, *, user: User, query: SearchQuery) -> set[uuid.UUID]:
    visible_ids = folder_access.visible_folder_ids(db, user)
    if not visible_ids:
        return set()

    if query.folder_id is None:
        return visible_ids

    if query.recursive:
        descendants = filesystem.collect_descendant_folder_ids(db, query.folder_id)
        return {folder_id for folder_id in descendants if folder_id in visible_ids}

    if query.folder_id not in visible_ids:
        return set()
    return {query.folder_id}

"""Composition root: wire concrete adapters for the application layer."""

from application.uow import UnitOfWork
from infra.db.uow_sqlalchemy import build_uow as _build_uow
from infra.object_storage.registry import build_storage_registry
from ports.storage_registry import StorageRegistry
from sqlalchemy.orm import Session


def build_uow(session: Session) -> UnitOfWork:
    return _build_uow(session)


__all__ = ["UnitOfWork", "build_storage_registry", "build_uow"]

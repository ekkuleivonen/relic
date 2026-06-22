"""Run application use cases inside a UnitOfWork commit boundary."""

from collections.abc import Callable
from typing import TypeVar

from application.uow import UnitOfWork
from composition import build_uow
from sqlalchemy.orm import Session

T = TypeVar("T")


def run_with_uow(db: Session, fn: Callable[[UnitOfWork], T]) -> T:
    uow = build_uow(db)
    try:
        result = fn(uow)
        uow.commit()
        return result
    except Exception:
        uow.rollback()
        raise
    finally:
        uow.close()

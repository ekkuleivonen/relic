from functools import lru_cache
from typing import Annotated

import settings as S
from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker


def get_database_url() -> str:
    return URL.create(
        drivername="postgresql+psycopg",
        username=S.POSTGRES_USER,
        password=S.POSTGRES_PASSWORD,
        host=S.POSTGRES_HOST,
        port=S.POSTGRES_PORT,
        database=S.POSTGRES_DB,
    ).render_as_string(hide_password=False)


def get_libpq_dsn() -> str:
    """libpq-style DSN for clients that bypass SQLAlchemy (e.g. psycopg async).

    SQLAlchemy URLs use the ``postgresql+psycopg://`` scheme; libpq only
    understands ``postgresql://``.
    """
    return URL.create(
        drivername="postgresql",
        username=S.POSTGRES_USER,
        password=S.POSTGRES_PASSWORD,
        host=S.POSTGRES_HOST,
        port=S.POSTGRES_PORT,
        database=S.POSTGRES_DB,
    ).render_as_string(hide_password=False)


@lru_cache
def get_engine():
    return create_engine(get_database_url(), pool_pre_ping=True)


@lru_cache
def get_sessionmaker():
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db():
    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]

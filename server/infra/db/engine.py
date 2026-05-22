from functools import lru_cache

import settings as S
from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker
from typing import Annotated


def get_database_url() -> str:
    if S.DATABASE_URL:
        return S.DATABASE_URL
    return URL.create(
        drivername="postgresql+psycopg",
        username=S.POSTGRES_USER,
        password=S.POSTGRES_PASSWORD,
        host=S.POSTGRES_HOST,
        port=S.POSTGRES_PORT,
        database=S.POSTGRES_DB,
    ).render_as_string(hide_password=False)


def get_libpq_dsn() -> str:
    """libpq-style DSN for clients that bypass SQLAlchemy (e.g. psycopg async)."""
    url = get_database_url()
    if url.startswith("postgresql+psycopg"):
        return url.replace("postgresql+psycopg", "postgresql", 1)
    if url.startswith("sqlite"):
        raise ValueError("libpq DSN is not available for SQLite URLs")
    return URL.create(
        drivername="postgresql",
        username=S.POSTGRES_USER,
        password=S.POSTGRES_PASSWORD,
        host=S.POSTGRES_HOST,
        port=S.POSTGRES_PORT,
        database=S.POSTGRES_DB,
    ).render_as_string(hide_password=False)


def detect_db_capabilities(engine):
    from infra.db.capabilities import detect_capabilities

    return detect_capabilities(engine)


@lru_cache
def get_engine():
    from infra.db.metrics import install_db_metrics

    engine = create_engine(get_database_url(), pool_pre_ping=True)
    install_db_metrics(engine)
    return engine


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

"""Test database helpers — schema via Alembic, not ``create_all``."""

import os
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool, StaticPool

_SERVER_DIR = Path(__file__).resolve().parents[1]


def create_test_engine() -> Engine:
    url = os.environ.get("TEST_DATABASE_URL", "sqlite://")
    if url.startswith("sqlite"):
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        @event.listens_for(engine, "connect")
        def _register_sqlite_functions(dbapi_connection, _connection_record) -> None:
            dbapi_connection.create_function(
                "now",
                0,
                lambda: datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
            )

        return engine

    return create_engine(url, poolclass=NullPool)


def upgrade_test_schema(engine: Engine) -> None:
    cfg = Config(str(_SERVER_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_SERVER_DIR / "alembic"))
    with engine.connect() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")

"""Database dialect capabilities for store adapter selection."""

from dataclasses import dataclass

from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class DbCapabilities:
    dialect: str
    json_path_queries: bool
    json_contains: bool
    partial_unique_indexes: bool
    skip_locked: bool


def detect_capabilities(engine: Engine) -> DbCapabilities:
    dialect = engine.dialect.name
    is_postgres = dialect == "postgresql"
    return DbCapabilities(
        dialect=dialect,
        json_path_queries=is_postgres,
        json_contains=is_postgres,
        partial_unique_indexes=dialect in ("postgresql", "sqlite"),
        skip_locked=dialect in ("postgresql", "sqlite"),
    )

from pathlib import Path
from logging.config import fileConfig

from alembic import context
from alembic.operations.ops import MigrationScript
from sqlalchemy import engine_from_config, pool

from database import get_database_url
from models import Base

config = context.config
config.set_main_option("sqlalchemy.url", get_database_url())

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_versions_dir() -> Path:
    script_location = Path(config.get_main_option("script_location"))
    if not script_location.is_absolute() and config.config_file_name:
        script_location = Path(config.config_file_name).parent / script_location
    return script_location / "versions"


def next_serial_revision_id() -> str:
    current = 0
    for migration_file in get_versions_dir().glob("*.py"):
        prefix = migration_file.name.split("_", 1)[0]
        if prefix.isdigit():
            current = max(current, int(prefix))
    return f"{current + 1:04d}"


def process_revision_directives(context, revision, directives) -> None:
    cmd_opts = getattr(config, "cmd_opts", None)
    if getattr(cmd_opts, "rev_id", None):
        return

    for directive in directives:
        if isinstance(directive, MigrationScript):
            directive.rev_id = next_serial_revision_id()


def run_migrations_offline() -> None:
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        process_revision_directives=process_revision_directives,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            process_revision_directives=process_revision_directives,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

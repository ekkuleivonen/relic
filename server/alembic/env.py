from pathlib import Path
from logging.config import fileConfig

from alembic import context
from alembic.operations.ops import MigrationScript
from sqlalchemy import engine_from_config, pool

from infra.db.engine import get_database_url
from infra.db.models import Base

config = context.config
config.set_main_option("sqlalchemy.url", get_database_url())

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
IGNORED_AUTOGENERATE_INDEXES = {
    "ix_files_meta_extension",
    "ix_files_meta_keywords",
    "ix_files_meta_mimetype",
    "ix_files_meta_tags",
}


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


def include_object(object, name, type_, reflected, compare_to):
    del object, compare_to
    if type_ == "index" and reflected and name in IGNORED_AUTOGENERATE_INDEXES:
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        process_revision_directives=process_revision_directives,
    )

    with context.begin_transaction():
        context.run_migrations()


def _configure_context(connection, **kwargs):
    render_as_batch = connection.dialect.name == "sqlite"
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        process_revision_directives=process_revision_directives,
        render_as_batch=render_as_batch,
        **kwargs,
    )


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _configure_context(connection)
        with context.begin_transaction():
            context.run_migrations()
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        _configure_context(connection)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

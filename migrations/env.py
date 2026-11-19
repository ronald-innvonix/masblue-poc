"""Async Alembic environment scoped to the service-owned schema."""

import asyncio
import re
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
schema = settings.db_schema
if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", schema):
    raise ValueError("DB_SCHEMA must be a simple lowercase PostgreSQL identifier")
config.set_main_option("sqlalchemy.url", settings.database_url)
config.attributes["db_schema"] = schema
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without a live connection using the configured schema."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        version_table_schema=schema,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        context.run_migrations()


def _do_run_migrations(connection: object) -> None:
    """Configure a sync migration context on an async engine's connection."""
    from sqlalchemy.engine import Connection
    from sqlalchemy.schema import CreateSchema

    if not isinstance(connection, Connection):
        raise TypeError("Expected a synchronous SQLAlchemy connection")
    connection.execute(CreateSchema(schema, if_not_exists=True))
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        version_table_schema=schema,
        compare_type=True,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


def include_name(name: str | None, type_: str, parent_names: dict[str, str]) -> bool:
    """Keep autogenerate reflection strictly inside the service-owned schema."""
    if type_ == "schema":
        return name == schema
    if type_ == "table":
        return parent_names.get("schema_name") == schema
    return True


async def _run_async_migrations() -> None:
    """Run migrations using SQLAlchemy's async engine support."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(_run_async_migrations())

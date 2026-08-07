"""How alembic reaches the database.

Async, because asyncpg is the only driver this module installs. The URL comes from the
module's own settings, so `DATABASE_URL` names the database for the service and for its
migrations alike; a test overrides it with `set_main_option("sqlalchemy.url", ...)`.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from market_data.db import sqlalchemy_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# No metadata to compare against, and none wanted: the tables are handwritten SQL and the
# runtime queries them through asyncpg, so there is no model layer for `--autogenerate` to
# diff. A migration here is read as the statement it will actually run.
target_metadata = None


def _database_url() -> str:
    configured = config.get_main_option("sqlalchemy.url", None)
    if configured:
        return configured
    # Imported lazily so that a test supplying its own URL never needs a DATABASE_URL in
    # the environment just to get this far.
    from market_data.config import Settings

    return sqlalchemy_url(Settings().database_url)


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    section = dict(config.get_section(config.config_ini_section) or {})
    section["sqlalchemy.url"] = _database_url()
    # NullPool because a migration run is one connection used once; a pool here would
    # only leave sockets open past the last statement.
    engine = async_engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())

"""How alembic reaches the database — duplicated from `agent/migrations/env.py` rather
than imported; see `teams/db.py`'s own docstring for why."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig
from urllib.parse import parse_qs, urlparse, urlunparse

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from teams.db import Credential, sqlalchemy_url

config = context.config

if config.config_file_name is not None:
    # `disable_existing_loggers=False` — see market_data's and agent's twins: alembic
    # runs in-process during tests, and the default would silently kill every `teams.*`
    # logger already created by importing the module.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = None


def _database_url() -> str:
    configured = config.get_main_option("sqlalchemy.url", None)
    if configured:
        return configured
    from teams.config import Settings

    return sqlalchemy_url(Settings().database_url)  # type: ignore[call-arg]


def _identity_connect_args() -> tuple[dict, Credential | None]:
    if config.get_main_option("sqlalchemy.url", None):
        return {}, None
    from teams.config import Settings
    from teams.db import identity_connect_args

    settings = Settings()  # type: ignore[call-arg]
    if settings.database_user is None:
        return {}, None
    return identity_connect_args(
        settings.database_user,
        settings.azure_client_id,
        settings.azure_client_secret,
        settings.azure_tenant_id,
    )


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
    database_url = _database_url()
    connect_args, credential = _identity_connect_args()
    if credential is not None:
        # See market_data's and agent's twins: SQLAlchemy's asyncpg dialect forwards a
        # URL's query string as literal kwargs to asyncpg.connect(), which does not
        # accept `sslmode=` — carried into connect_args as `ssl` instead.
        parsed = urlparse(database_url)
        sslmode = parse_qs(parsed.query).get("sslmode", [None])[0]
        if sslmode:
            connect_args["ssl"] = sslmode
        database_url = urlunparse(parsed._replace(query=""))
    section["sqlalchemy.url"] = database_url
    engine = async_engine_from_config(
        section, prefix="sqlalchemy.", poolclass=pool.NullPool, connect_args=connect_args
    )
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run_migrations)
    finally:
        await engine.dispose()
        if credential is not None:
            await credential.close()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())

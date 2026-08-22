"""How alembic reaches the database.

Async, because asyncpg is the only driver this module installs. The URL comes from the
module's own settings, so `DATABASE_URL` names the database for the service and for its
migrations alike; a test overrides it with `set_main_option("sqlalchemy.url", ...)`.

The identity path is the point rather than a detail: migrations run as the same role the
module later works as, so a table a migration creates is usable without a grant nobody
remembers to make.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig
from urllib.parse import parse_qs, urlparse, urlunparse

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from tc_runtime.db import Credential, sqlalchemy_url

config = context.config

if config.config_file_name is not None:
    # `disable_existing_loggers=False`, against `fileConfig`'s default. Alembic runs
    # in-process during tests, and the default switches off every logger that already
    # exists — which is every `polymarket_data.*` logger, since importing the module
    # created them. A test asserting on what is logged would then pass for the wrong
    # reason.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# No metadata to compare against, and none wanted: the tables are handwritten SQL and the
# runtime queries them through asyncpg, so there is no model layer for `--autogenerate` to
# diff.
target_metadata = None


def _database_url() -> str:
    configured = config.get_main_option("sqlalchemy.url", None)
    if configured:
        return configured
    # Imported lazily so that a test supplying its own URL never needs a DATABASE_URL in
    # the environment just to get this far.
    from polymarket_data.config import Settings

    return sqlalchemy_url(Settings().database_url)  # type: ignore[call-arg]


def _identity_connect_args() -> tuple[dict, Credential | None]:
    """Identity auth for the engine this migration run drives — the same mechanism the
    application uses, so a migration proves the role it runs as can do what the running
    module will later need. Empty when a test has already pointed `sqlalchemy.url` at its
    own throwaway database, or in local mode, where the URL carries its own credential."""
    if config.get_main_option("sqlalchemy.url", None):
        return {}, None
    from tc_runtime.db import identity_connect_args

    from polymarket_data.config import Settings

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
        # SQLAlchemy's asyncpg dialect forwards a URL's query string as literal keyword
        # arguments to `asyncpg.connect()` — `?sslmode=require` becomes an `sslmode=`
        # kwarg, which asyncpg does not accept. Carried into connect_args as `ssl`
        # instead, and the query string dropped so it cannot be passed along twice.
        parsed = urlparse(database_url)
        sslmode = parse_qs(parsed.query).get("sslmode", [None])[0]
        if sslmode:
            connect_args["ssl"] = sslmode
        database_url = urlunparse(parsed._replace(query=""))
    section["sqlalchemy.url"] = database_url
    # NullPool because a migration run is one connection used once.
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

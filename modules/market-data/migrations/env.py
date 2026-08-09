"""How alembic reaches the database.

Async, because asyncpg is the only driver this module installs. The URL comes from the
module's own settings, so `DATABASE_URL` names the database for the service and for its
migrations alike; a test overrides it with `set_main_option("sqlalchemy.url", ...)`.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig
from urllib.parse import parse_qs, urlparse, urlunparse

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from market_data.db import sqlalchemy_url

config = context.config

if config.config_file_name is not None:
    # `disable_existing_loggers=False`, against `fileConfig`'s default. Alembic runs
    # in-process during tests (the migrated container in `conftest.py`), and the default
    # switches off every logger that already exists — which is every `market_data.*`
    # logger, since importing the module created them. The module then runs with its
    # logging silently dead, so a test asserting on what is and is not logged passes for
    # the wrong reason and would keep passing if the line it checks were deleted.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

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


def _identity_connect_args() -> tuple[dict, object | None]:
    """Identity auth for the engine this migration run drives — the same mechanism
    `db.py` uses for the application itself, so a migration proves the role it runs as
    can do exactly what the running module will later need (specs/market-data-database-
    connection). Empty when a test has already pointed `sqlalchemy.url` at its own
    throwaway database (`_database_url()` above) — that connection carries its own
    credential in the URL and has no module identity to speak of.
    """
    if config.get_main_option("sqlalchemy.url", None):
        return {}, None
    from market_data.config import Settings
    from market_data.db import identity_connect_args

    settings = Settings()
    # Local mode: no DATABASE_USER means the URL carries its own credential and points
    # at loopback (config.py enforces both), so the engine needs no identity arguments —
    # the same shape as a test's throwaway database.
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
        # arguments to `asyncpg.connect()` — `?sslmode=require` becomes a `sslmode=`
        # kwarg, which asyncpg does not accept (it wants `ssl=`, and only when passed
        # explicitly rather than through the DSN). asyncpg.connect() itself parses
        # `sslmode` out of a DSN string fine, which is why `pool()`/`connect()` in
        # db.py never need this: they hand asyncpg the DSN whole and never go through
        # SQLAlchemy's URL/kwarg split. The mode still means something — carried into
        # connect_args as `ssl` instead, and the query string dropped so SQLAlchemy
        # cannot pass it along a second time.
        parsed = urlparse(database_url)
        sslmode = parse_qs(parsed.query).get("sslmode", [None])[0]
        if sslmode:
            connect_args["ssl"] = sslmode
        database_url = urlunparse(parsed._replace(query=""))
    section["sqlalchemy.url"] = database_url
    # NullPool because a migration run is one connection used once; a pool here would
    # only leave sockets open past the last statement.
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

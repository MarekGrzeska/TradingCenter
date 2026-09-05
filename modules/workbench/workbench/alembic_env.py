"""How alembic reaches a database — one copy for both chains, which were byte-identical outside their comments.
Alembic executes each `env.py` as a script, so the import below resolves against `sys.path`."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from logging.config import fileConfig
from urllib.parse import parse_qs, urlparse, urlunparse

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from tc_runtime.db import sqlalchemy_url

# Neither chain autogenerates: the migrations are handwritten SQL, so alembic has no
# metadata to compare against.
TARGET_METADATA = None

# What a caller hands in: a function returning the settings of the surface whose database
# this chain belongs to.
SurfaceSettings = Callable[[], object]


def run(settings_for_surface: SurfaceSettings) -> None:
    """The whole of an `env.py`. Called at import time by each chain's own file."""
    config = context.config

    if config.config_file_name is not None:
        # `disable_existing_loggers=False` — alembic runs in-process during tests, and the default would silently kill
        # every logger already created by importing the package under test.
        fileConfig(config.config_file_name, disable_existing_loggers=False)

    if context.is_offline_mode():
        _run_offline(config, settings_for_surface)
    else:
        asyncio.run(_run_online(config, settings_for_surface))


def _database_url(config, settings_for_surface: SurfaceSettings) -> str:
    configured = config.get_main_option("sqlalchemy.url", None)
    if configured:
        return configured
    return sqlalchemy_url(settings_for_surface().database_url)  # type: ignore[attr-defined]


def _identity_connect_args(config, settings_for_surface: SurfaceSettings):
    if config.get_main_option("sqlalchemy.url", None):
        return {}, None
    from tc_runtime.db import identity_connect_args

    settings = settings_for_surface()
    if settings.database_user is None:  # type: ignore[attr-defined]
        return {}, None
    return identity_connect_args(
        settings.database_user,  # type: ignore[attr-defined]
        settings.azure_client_id,  # type: ignore[attr-defined]
        settings.azure_client_secret,  # type: ignore[attr-defined]
        settings.azure_tenant_id,  # type: ignore[attr-defined]
    )


def _run_offline(config, settings_for_surface: SurfaceSettings) -> None:
    context.configure(
        url=_database_url(config, settings_for_surface),
        target_metadata=TARGET_METADATA,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=TARGET_METADATA)
    with context.begin_transaction():
        context.run_migrations()


async def _run_online(config, settings_for_surface: SurfaceSettings) -> None:
    section = dict(config.get_section(config.config_ini_section) or {})
    database_url = _database_url(config, settings_for_surface)
    connect_args, credential = _identity_connect_args(config, settings_for_surface)
    if credential is not None:
        # See market_data's twin: SQLAlchemy's asyncpg dialect forwards a URL's query string as literal kwargs to
        # `asyncpg.connect()`, which does not accept `sslmode=` — carried into connect_args as `ssl` instead.
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


def conversation_settings():
    """Imported lazily, and inside the call: building `Settings()` reads the environment,
    which a test overriding `sqlalchemy.url` has deliberately emptied."""
    from workbench.config import Settings

    return Settings().for_conversation()  # type: ignore[call-arg]


def teams_settings():
    from workbench.config import Settings

    return Settings().for_teams()  # type: ignore[call-arg]


def polymarket_settings() -> object:
    """The prediction-market archive's chain — the third database this process migrates."""
    from workbench.config import Settings

    return Settings().for_polymarket()  # type: ignore[call-arg]


def social_settings() -> object:
    """The post archive's chain — the fourth."""
    from workbench.config import Settings

    return Settings().for_social()  # type: ignore[call-arg]


def strategy_settings() -> object:
    """The strategy platform's chain — the fifth."""
    from workbench.config import Settings

    return Settings().for_strategy()  # type: ignore[call-arg]

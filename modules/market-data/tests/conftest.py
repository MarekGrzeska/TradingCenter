"""Shared fixtures — chiefly the throwaway PostgreSQL the `db` tests run against.

A container per test session rather than a shared development database, because the
schema is part of what is under test here. A table left behind by a previous run is
indistinguishable from a migration that works, and that is exactly the failure this
module cannot afford: the archive's correctness *is* its schema.

Docker is not assumed. Without it the `db` tests skip with a reason that says what to
start, instead of failing with a connection error that reads like a bug in the code.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import asyncpg
import pytest

from market_data.db import asyncpg_dsn, sqlalchemy_url

MODULE_ROOT = Path(__file__).resolve().parent.parent

# Emptied between tests so that one test's rows are never another's premise. TRUNCATE
# rather than dropping and re-migrating: the schema is the same for every test, and
# re-running three migrations per test buys nothing.
TABLES = ("candles", "tracked_pairs", "coverage_ranges")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if _docker_is_usable():
        return
    skip = pytest.mark.skip(reason="needs a running Docker daemon for the PostgreSQL container")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)


def _docker_is_usable() -> bool:
    try:
        import docker
    except ImportError:
        return False
    try:
        # A short timeout on purpose. The default waits about a minute for a daemon that
        # is not running, which turns every test run on a machine without Docker into a
        # minute of silence before the same skip. A daemon that cannot answer a ping in
        # two seconds is not one the container fixture would have succeeded against.
        docker.from_env(timeout=2).ping()
    except Exception:  # noqa: BLE001 - any failure here means "no usable daemon"
        return False
    return True


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """A URL to an empty PostgreSQL, alive for the session and gone afterwards."""
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:17-alpine", driver=None) as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def migrated_url(postgres_url: str) -> str:
    """The same database with the module's migrations applied.

    Applied by running alembic itself rather than by a hand-written CREATE TABLE in the
    fixture. A fixture that builds its own schema tests a schema no deployment will ever
    have, and the migration — the thing that has to work in production — goes unrun.

    Synchronous on purpose: alembic's async environment calls `asyncio.run`, which needs
    a thread with no loop already running. A sync fixture is such a thread; an async one
    is not.
    """
    from alembic import command
    from alembic.config import Config

    config = Config(str(MODULE_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(MODULE_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", sqlalchemy_url(postgres_url))
    command.upgrade(config, "head")
    return postgres_url


@pytest.fixture
async def db(migrated_url: str) -> AsyncIterator[asyncpg.Connection]:
    """A connection to the migrated database, with the tables emptied first."""
    conn = await asyncpg.connect(asyncpg_dsn(migrated_url))
    try:
        await conn.execute(f"TRUNCATE {', '.join(TABLES)}")
        yield conn
    finally:
        await conn.close()

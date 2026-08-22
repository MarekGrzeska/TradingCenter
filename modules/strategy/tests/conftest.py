"""Shared fixtures — chiefly the throwaway PostgreSQL the `db` tests run against.

A container per test session rather than a shared development database, because the schema
is part of what is under test: a table left behind by a previous run is indistinguishable
from a migration that works.

Docker is not assumed. Without it the `db` tests skip with a reason that says what to
start, instead of failing with a connection error that reads like a bug in the code.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import asyncpg
import httpx
import pytest
from tc_runtime.db import asyncpg_dsn, sqlalchemy_url

from strategy.app import create_app
from strategy.config import Settings

MODULE_ROOT = Path(__file__).resolve().parent.parent

# Testcontainers' reaper is a sidecar that bind-mounts the Docker socket. On Docker Desktop
# for macOS that socket lives under the user's home directory, which the VM refuses to
# mount, and every `db` test then fails on a container that will not start. Safe to
# disable here because the container fixture is a context manager: normal runs, failing
# runs and Ctrl-C all stop it on the way out.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

# Emptied between tests so that one test's rows are never another's premise. TRUNCATE
# rather than dropping and re-migrating: the schema is the same for every test.
TABLES = ("decisions", "watches", "parameter_sets", "backtest_runs")

# Generous, because Docker Desktop wakes its VM lazily and a first call after an idle
# spell can take several seconds.
DOCKER_PING_TIMEOUT = 15

DOCKER_SOCKETS = (
    Path("/var/run/docker.sock"),
    Path.home() / ".docker/run/docker.sock",
    Path.home() / ".colima/default/docker.sock",
    Path.home() / ".rd/docker.sock",
)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    reason = _reason_to_skip_db_tests()
    if reason is None:
        return
    skip = pytest.mark.skip(reason=reason)
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)


def _reason_to_skip_db_tests() -> str | None:
    """Why the `db` tests cannot run here, or `None` to let them run.

    Only a machine with no Docker at all earns a skip. A daemon that is installed and
    failing does not: a silent skip on a machine that was supposed to have Docker is
    indistinguishable from a suite that passed.
    """
    try:
        import docker
    except ImportError:
        return "the docker package is not installed"

    try:
        docker.from_env(timeout=DOCKER_PING_TIMEOUT).ping()
    except Exception as err:  # noqa: BLE001 - any failure here means "not answering"
        if _docker_is_installed():
            print(f"\ndocker is installed but not answering ({err}); running `db` tests anyway")
            return None
        return "no Docker daemon for the PostgreSQL container"
    return None


def _docker_is_installed() -> bool:
    return bool(os.environ.get("DOCKER_HOST")) or any(
        socket.exists() for socket in DOCKER_SOCKETS
    )


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """A URL to an empty PostgreSQL, alive for the session and gone afterwards."""
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:17-alpine", driver=None) as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def migrated_url(postgres_url: str) -> str:
    """The same database with this module's migrations applied.

    Applied by running alembic itself rather than by a hand-written CREATE TABLE in the
    fixture: a fixture that builds its own schema tests a schema no deployment will ever
    have, and the migration — the thing that has to work in production — goes unrun.

    Synchronous on purpose: alembic's async environment calls `asyncio.run`, which needs a
    thread with no loop already running.
    """
    from tc_runtime.migrate import upgrade_to_head

    from strategy.runtime import MIGRATIONS

    upgrade_to_head(MIGRATIONS, sqlalchemy_url(postgres_url))
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


@pytest.fixture
async def pool(migrated_url: str):
    from tc_runtime.db import pool as make_pool

    async with make_pool(migrated_url, max_size=5) as created:
        async with created.acquire() as conn:
            await conn.execute(f"TRUNCATE {', '.join(TABLES)}")
        yield created


@pytest.fixture
def settings() -> Settings:
    """What the application reads about itself, minus anything that reaches outward.

    Every fixture that *serves* the app needs these, not only the ones that touch the
    database: `caller_access.py` reads `require_authenticated_principal` on every request
    and refuses when the settings are missing.

    The database URL is metadata only — the pool the fixtures build is what actually
    reaches PostgreSQL. A throwaway value that satisfies Settings' own rules (TLS
    required, no embedded credential) rather than `migrated_url`, which as testcontainers
    hands it out is neither.
    """
    return Settings(
        database_url="postgresql://localhost:5432/test?sslmode=require",
        database_user="test-user",
        _env_file=None,
    )


@pytest.fixture
def app():
    """A fresh application per test, so no test's `app.state` survives into the next."""
    return create_app()


@pytest.fixture
async def api(app, pool, settings):
    """The app wired to a real database, with the lifespan bypassed.

    The lifespan is not run: it would migrate (the fixture already did) and start the
    loop, which would reach an archive that is not there. What is under test here is the
    contract.
    """
    app.state.pool = pool
    app.state.settings = settings

    # `raise_app_exceptions=False` so the app's own error handling is what the test sees.
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://strategy.test") as client:
        yield client

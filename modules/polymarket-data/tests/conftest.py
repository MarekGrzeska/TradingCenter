"""Shared fixtures — chiefly the throwaway PostgreSQL the `db` tests run against, a container per
session because the schema is part of what is under test. Without Docker they skip, saying what to start."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import asyncpg
import pytest
from tc_runtime.db import asyncpg_dsn, sqlalchemy_url

from polymarket_data.app import create_app
from polymarket_data.config import Settings

MODULE_ROOT = Path(__file__).resolve().parent.parent

# Testcontainers' reaper bind-mounts the Docker socket, which Docker Desktop for macOS refuses. Safe
# to disable here: the container fixture is a context manager, so only a SIGKILL of pytest leaks one.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

# Emptied between tests so one test's rows are never another's premise. TRUNCATE rather than
# re-migrating, and named in full rather than left to CASCADE, so the statement says what it empties.
TABLES: tuple[str, ...] = (
    "price_samples",
    "collected_ranges",
    "sampling_state",
    "outcomes",
    "markets",
    "tracked_events",
    "observation_groups",
)

# Generous, because Docker Desktop wakes its VM lazily and a first call after an idle spell
# can take several seconds.
DOCKER_PING_TIMEOUT = 15

DOCKER_SOCKETS = (
    Path("/var/run/docker.sock"),
    Path.home() / ".docker/run/docker.sock",
    Path.home() / ".colima/default/docker.sock",
    Path.home() / ".rd/docker.sock",
)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="run tests that read the real Polymarket API over the network",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not config.getoption("--run-live"):
        skip_live = pytest.mark.skip(reason="needs --run-live and a reachable Polymarket API")
        for item in items:
            if "live" in item.keywords:
                item.add_marker(skip_live)

    reason = _reason_to_skip_db_tests()
    if reason is None:
        return
    skip = pytest.mark.skip(reason=reason)
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)


def _reason_to_skip_db_tests() -> str | None:
    """Why the `db` tests cannot run here, or `None` to let them run. Only a machine with no Docker at
    all earns a skip: a silent skip where Docker was expected is indistinguishable from a pass."""
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
    """The same database with the module's migrations applied — by running alembic, because a fixture
    that builds its own schema tests one no deployment will have. Synchronous: alembic calls `asyncio.run`."""
    from tc_runtime.migrate import upgrade_to_head

    from polymarket_data.runtime import MIGRATIONS

    upgrade_to_head(MIGRATIONS, sqlalchemy_url(postgres_url))
    return postgres_url


@pytest.fixture
async def db(migrated_url: str) -> AsyncIterator[asyncpg.Connection]:
    """A connection to the migrated database, with the tables emptied first."""
    conn = await asyncpg.connect(asyncpg_dsn(migrated_url))
    try:
        if TABLES:
            await conn.execute(f"TRUNCATE {', '.join(TABLES)}")
        yield conn
    finally:
        await conn.close()


@pytest.fixture
def settings() -> Settings:
    """What the application reads about itself, minus anything that reaches outward. The database URL is
    metadata only: a throwaway value satisfying Settings' rules, which `migrated_url` does not."""
    return Settings(
        database_url="postgresql://localhost:5432/test?sslmode=require",
        database_user="test-user",
        _env_file=None,
    )


@pytest.fixture
async def pool(migrated_url: str):
    """A pool over the migrated database, emptied first — what `Ingest` takes."""
    from tc_runtime.db import pool as make_pool

    async with make_pool(migrated_url, max_size=5) as created:
        async with created.acquire() as conn:
            await conn.execute(f"TRUNCATE {', '.join(TABLES)}")
        yield created


class RecordingIngest:
    """Stands in for the sampler, and records what tracking asked it to fill. Until that call existed the
    ninety days a caller is promised arrived only at the next process restart."""

    def __init__(self) -> None:
        self.backfilled: list[int] = []

    def event_tracked(self, event_id: int) -> None:
        self.backfilled.append(event_id)


@pytest.fixture
async def api(app, pool, settings):
    """The app wired to a real database, with the provider faked. The lifespan is bypassed rather than
    run: it would start the sampler, which would reach a third party over the network."""
    import fakes
    import httpx

    app.state.pool = pool
    app.state.settings = settings
    app.state.provider = fakes.FakeProvider()
    app.state.ingest = RecordingIngest()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://tests") as client:
        yield client


@pytest.fixture
async def tool_server(app, pool, settings):
    """The FastMCP server this module publishes, wired to a real database and built from the same
    application `create_app()` builds — a server assembled here would be a ceiling on nothing."""
    import fakes

    app.state.pool = pool
    app.state.settings = settings
    app.state.provider = fakes.FakeProvider()
    app.state.ingest = RecordingIngest()
    return app.state.mcp_server


@pytest.fixture
def app():
    """A fresh application per test. A fixture rather than an import: while the module-level `app` was in
    scope, a test that forgot to ask for this one still found something to mutate."""
    return create_app()

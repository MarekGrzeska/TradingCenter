"""Shared fixtures — chiefly the throwaway PostgreSQL the `db` tests run against, a container per
session because the schema is part of what is under test. Without Docker they skip, saying what to start."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from datetime import timedelta
from pathlib import Path

import asyncpg
import httpx
import pytest
from fakes import FakeIngest, FakeInstruments, FakeJobRunner

from market_data.app import create_app
from market_data.config import Settings
from market_data.db import asyncpg_dsn, sqlalchemy_url
from market_data.hub import Hub
from market_data.market_status import MarketStatus
from market_data.tickets import TicketStore

MODULE_ROOT = Path(__file__).resolve().parent.parent

# Testcontainers' reaper bind-mounts the Docker socket, which Docker Desktop for macOS refuses. Safe
# to disable here: the container fixture is a context manager, so only a SIGKILL of pytest leaks one.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

# Emptied between tests so one test's rows are never another's premise. TRUNCATE rather than
# re-migrating: the schema is the same for every test.
TABLES = (
    "candles",
    "derived_candles",
    "tracked_pairs",
    "coverage_ranges",
    "collection_jobs",
    "collection_job_chunks",
    "pair_deletions",
)


# Generous, because Docker Desktop wakes its VM lazily. The earlier two-second budget read a cold
# daemon as an absent one, and thirty tests skipped where they would have passed.
DOCKER_PING_TIMEOUT = 15

# Where a daemon's socket lives, if there is one. Used only to tell "Docker was never
# installed here" from "Docker is installed and unwell".
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
        help="run tests that read through a running capital-gateway on the demo API",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not config.getoption("--run-live"):
        skip_live = pytest.mark.skip(reason="needs --run-live and a running capital-gateway")
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

    from market_data.runtime import MIGRATIONS

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
def settings() -> Settings:
    """What the application reads about itself, minus anything that reaches outward. Every fixture that
    serves the app needs these: `caller_access.py` refuses when the settings are missing."""
    return Settings(
        database_url="postgresql://localhost:5432/test?sslmode=require",
        database_user="test-user",
        gateway_api_key="test-gateway-key",
        _env_file=None,
    )


@pytest.fixture
def app():
    """A fresh application per test. A fixture rather than an import: while the module-level `app` was in
    scope, twenty tests reassigned `app.state.*` and every assignment survived into the next."""
    return create_app()


@pytest.fixture
async def pool(migrated_url: str):
    from market_data.db import pool as make_pool

    async with make_pool(migrated_url, max_size=5) as created:
        async with created.acquire() as conn:
            await conn.execute(f"TRUNCATE {', '.join(TABLES)}")
        yield created


@pytest.fixture
async def api(app, pool, settings, migrated_url: str):
    """The app wired to a real database, with the two things that reach outward faked. The lifespan is
    bypassed rather than run: it would start ingest against a gateway that is not there."""
    app.state.pool = pool
    app.state.hub = Hub()
    app.state.settings = settings
    app.state.instruments = FakeInstruments()
    app.state.ingest = FakeIngest()
    app.state.market_status = MarketStatus()
    app.state.job_runner = FakeJobRunner()
    app.state.tickets = TicketStore(timedelta(seconds=30))

    # `raise_app_exceptions=False` so the app's own error handling is what the test sees. With the
    # default, the transport re-raises and the 500 the handler produced never reaches the response.
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://archive.test") as client:
        yield client


# These tests came from a separate module, where the seam was an HTTP client. The seam is now the
# `reads` layer, so the double sits there; what is under test is unchanged.


@pytest.fixture
def archive():
    from tools_double import FakeArchive

    return FakeArchive()


@pytest.fixture
def tool_server(archive, monkeypatch: pytest.MonkeyPatch):
    """A FastMCP server whose tools read the double, with the output-schema check put back. `FastMCP.
    call_tool` skips it, so a tool can be green in CI and refuse itself on every real call."""
    import jsonschema

    from market_data.indicators import service
    from market_data.mcp_app import build_server
    from market_data.tools import _shared, candles, indicators, resources

    class _FakeConnection:
        pass

    class _FakePool:
        def acquire(self):
            class _Held:
                async def __aenter__(self_inner):
                    return _FakeConnection()

                async def __aexit__(self_inner, *_exc):
                    return False

            return _Held()

    class _FakeState:
        pool = _FakePool()
        hub = Hub()
        instruments = FakeInstruments()
        market_status = MarketStatus()
        indicator_limiter = _NullLimiter()

    class _FakeApp:
        state = _FakeState()

    async def read_series(_conn, symbol, resolution, start, end):
        archive.reads.append(("series", symbol, resolution, start, end))
        if archive.series_error is not None:
            raise archive.series_error
        return archive.next_series()

    async def read_forming(_conn, _hub, _instruments, _status, symbol, resolution):
        archive.reads.append(("forming", symbol, resolution))
        return archive.forming

    async def read_pair_coverage(_conn, symbol, resolution):
        archive.reads.append(("coverage", symbol, resolution))
        return archive.coverage

    async def read_pairs(_conn, _instruments, _status, _now):
        return [(pair, pair.collection) for pair in archive.pairs]

    async def compute(symbol, body, _db, _limiter):
        archive.computations.append((symbol, body))
        if archive.compute_error is not None:
            raise archive.compute_error
        if archive.compute_with is not None:
            return archive.compute_with(symbol, body)
        assert archive.computed is not None, "the test did not set archive.computed"
        return archive.computed

    monkeypatch.setattr(candles, "read_series", read_series)
    monkeypatch.setattr(candles, "read_forming", read_forming)
    monkeypatch.setattr(candles, "read_pair_coverage", read_pair_coverage)
    monkeypatch.setattr(resources, "read_pair_coverage", read_pair_coverage)
    monkeypatch.setattr(indicators, "read_series", read_series)
    monkeypatch.setattr(_shared, "read_pairs", read_pairs)
    monkeypatch.setattr(service, "compute", compute)

    app = _FakeApp()
    mcp = build_server(app)
    _check_output_schema(mcp, jsonschema)
    mcp._fake_app = app  # so a test can reach the instruments double
    return mcp


class _NullLimiter:
    """The indicator semaphore, held open. The real ceiling has its own test."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


def _check_output_schema(mcp, jsonschema) -> None:
    original = mcp.call_tool
    schemas: dict = {}

    async def checked(name: str, arguments: dict, **kwargs):
        content, structured = await original(name, arguments, **kwargs)
        if not schemas:
            schemas.update({tool.name: tool.outputSchema for tool in await mcp.list_tools()})
        schema = schemas.get(name)
        if schema is not None and structured is not None:
            jsonschema.validate(instance=structured, schema=schema)
        return content, structured

    mcp.call_tool = checked  # type: ignore[method-assign]

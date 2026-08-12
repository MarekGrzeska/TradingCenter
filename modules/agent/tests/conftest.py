"""Shared fixtures — chiefly the throwaway PostgreSQL the `db` tests run against.

Duplicated from `market_data/tests/conftest.py` rather than imported — no shared library
between modules, and this module's schema is its own thing to prove correct.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import asyncpg
import pytest

from agent.db import asyncpg_dsn, sqlalchemy_url

MODULE_ROOT = Path(__file__).resolve().parent.parent

# See market_data's twin: the reaper's Docker-socket bind-mount fails on Docker Desktop
# for macOS, and the container fixture already stops cleanly on its own.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

# Children before parents: `tool_calls` and `usage` both reference `messages`.
TABLES = ("tool_calls", "usage", "messages", "sessions")

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
        help="run tests that call a real OpenAI model",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not config.getoption("--run-live"):
        skip_live = pytest.mark.skip(reason="needs --run-live and a configured OpenAI key")
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
    """The same database with the module's migrations applied — run through alembic
    itself, so the schema under test is the one a deployment will actually apply."""
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
        await conn.execute(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE")
        yield conn
    finally:
        await conn.close()


@pytest.fixture
async def pool(db: asyncpg.Connection, migrated_url: str) -> AsyncIterator[asyncpg.Pool]:
    """A pool over the same emptied database `db` connects to — `turn.py` takes a pool,
    not a bare connection, because a turn acquires twice (history, then the reply)."""
    created = await asyncpg.create_pool(asyncpg_dsn(migrated_url))
    try:
        yield created
    finally:
        await created.close()

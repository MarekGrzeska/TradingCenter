"""Shared fixtures — chiefly the throwaway PostgreSQL the `db` tests run against.

Duplicated from `agent/tests/conftest.py` rather than imported — no shared library
between modules, and this module's schema is its own thing to prove correct.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import asyncpg
import pytest

from teams.db import asyncpg_dsn, sqlalchemy_url

MODULE_ROOT = Path(__file__).resolve().parent.parent

# See market_data's and agent's twins: the reaper's Docker-socket bind-mount fails on
# Docker Desktop for macOS, and the container fixture already stops cleanly on its own.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

# Children before parents: `usage` and `tool_calls` both reference `run_steps`,
# `run_steps` references `runs`, `runs` references `team_revisions`, `team_revisions`
# references `teams` — the same convention agent's own TABLES follows. `schedule_fires`
# references `schedules`, `triggers` and `runs`; `schedules` and `triggers` each
# reference `team_revisions`.
TABLES: tuple[str, ...] = (
    "usage",
    "tool_calls",
    "schedule_fires",
    "run_steps",
    "runs",
    "schedules",
    "triggers",
    "team_revisions",
    "teams",
)

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
    """The same database with the module's migrations applied — through the same
    function the module runs at startup, so the schema under test is the one a
    deployment actually applies rather than a second arrangement that resembles it.
    """
    from teams.migrate import upgrade_to_head

    upgrade_to_head(sqlalchemy_url(postgres_url))
    return postgres_url


@pytest.fixture
async def db(migrated_url: str) -> AsyncIterator[asyncpg.Connection]:
    """A connection to the migrated database, with any owned tables emptied first."""
    conn = await asyncpg.connect(asyncpg_dsn(migrated_url))
    try:
        if TABLES:
            await conn.execute(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE")
        yield conn
    finally:
        await conn.close()


@pytest.fixture
async def pool(db: asyncpg.Connection, migrated_url: str) -> AsyncIterator[asyncpg.Pool]:
    """A pool over the same emptied database `db` connects to."""
    created = await asyncpg.create_pool(asyncpg_dsn(migrated_url))
    try:
        yield created
    finally:
        await created.close()

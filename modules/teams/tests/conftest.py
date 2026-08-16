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
# reference `team_revisions`. `team_layouts` references `teams` directly, not a revision.
TABLES: tuple[str, ...] = (
    "trades",
    "usage",
    "tool_calls",
    "schedule_fires",
    "run_steps",
    "runs",
    "schedules",
    "triggers",
    "team_layouts",
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


# Settings whose *absence* a test can depend on, and which a developer's `.env` supplies.
# Blank rather than deleted, because deleting is what does not work: `Settings` reads
# `.env` through pydantic-settings, and an environment variable removed from the process
# uncovers the file's value instead of hiding it — `monkeypatch.delenv` there makes a test
# read the developer's own market-mcp. An empty value is a value, it wins over the file,
# and `config.py` already reads a blank optional setting as unset
# (`test_config.py::test_a_blank_tool_server_url_means_unset`). CI has no `.env` at all,
# so this is the difference between a suite that is green there and green anywhere.
_BLANK_LOCALLY = ("MARKET_MCP_URL", "MARKET_MCP_SCOPE", "DATABASE_USER")

# The Entra triple is the exception, and it is the other consumer that makes it one:
# `DefaultAzureCredential` reads these out of the process environment itself, and it reads
# an empty `AZURE_CLIENT_ID` as a broken one rather than as an absent one
# (`ValueError: client_id should be the id of a Microsoft Entra application`). Deleted, not
# blanked — and deletion is enough here, because what must not see them is azure-identity,
# which never looks at `.env`.
_DELETED_LOCALLY = ("AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID")


@pytest.fixture(autouse=True)
def _no_developer_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The module's own `.env`, kept out of every test that builds `Settings()` itself —
    which is every test going through `TestClient(app)`, since the lifespan is where the
    settings are read. A test wanting one of these sets it with `monkeypatch.setenv`,
    which wins over both this and the file."""
    for name in _BLANK_LOCALLY:
        monkeypatch.setenv(name, "")
    for name in _DELETED_LOCALLY:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("REQUIRE_AUTHENTICATED_PRINCIPAL", "false")


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

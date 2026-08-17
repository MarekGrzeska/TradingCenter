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

from teams.config import Settings
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


@pytest.fixture(autouse=True)
def _no_developer_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every source of settings a developer's machine has and CI does not, taken away
    from each test that builds `Settings()` itself — which is every test going through
    `TestClient(app)`, since the lifespan is where the settings are read. A test wanting
    one of them sets it with `monkeypatch.setenv`, which is read after this.

    Two sources, and neither is covered by handling the other:

    * the module's `.env`, switched off at the class rather than name by name. An earlier
      version of this fixture blanked a list of names instead, and the list went stale the
      moment `TRADING_MCP_URL` was added — six tests that assert "no tool server
      configured" passed in CI and failed on a machine with an `.env`. Blanking was itself
      a workaround for `delenv` uncovering the file's value; with the file out of the
      picture there is nothing left to uncover, so deletion works and no list is needed.
    * the process environment, which is the shell's and not the file's. `Settings` fields
      map one-to-one onto variable names here (no `env_prefix`), so deleting all of them
      needs no list either — and it is what keeps `AZURE_CLIENT_ID` away from
      `DefaultAzureCredential`, the one consumer that reads the environment itself and
      would take a blank value for a broken one rather than an absent one.
    """
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)


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

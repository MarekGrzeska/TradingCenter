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
from tc_runtime.db import asyncpg_dsn, sqlalchemy_url

from agent.config import Settings

MODULE_ROOT = Path(__file__).resolve().parent.parent

# See market_data's twin: the reaper's Docker-socket bind-mount fails on Docker Desktop
# for macOS, and the container fixture already stops cleanly on its own.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

# Children before parents: `tool_calls` and `usage` both reference `messages`, and
# `chart_commands` and `chart_drawings` reference `sessions`.
TABLES = ("chart_drawings", "chart_commands", "tool_calls", "usage", "messages", "sessions")

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


@pytest.fixture(autouse=True)
def _no_developer_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every source of settings a developer's machine has and CI does not, taken away
    from each test that builds `Settings()` itself — which is every test going through
    `TestClient(app)`, since the lifespan is where the settings are read. A test wanting
    one of them sets it with `monkeypatch.setenv`, which is read after this.

    Without this the suite is green in CI, which has no `.env`, and *hangs* on a machine
    that has one: a `MARKET_MCP_URL` or `TEAMS_MCP_URL` naming a tool server nobody is
    serving leaves `test_send_message_streams_fragments_then_completes` waiting inside its
    POST rather than failing (measured 17 August 2026 — 5 seconds without the file, no
    end with it).

    Two sources, and neither is covered by handling the other:

    * the module's `.env`, switched off at the class rather than name by name — a list of
      names is what goes stale the next time a setting is added, which is how `teams`'
      twin of this fixture came to miss `TRADING_MCP_URL`. Deleting the variables is
      enough only because the file is gone; while it is read, a deleted variable uncovers
      the file's value instead of hiding it.
    * the process environment, which is the shell's and not the file's. `Settings` fields
      map one-to-one onto variable names here (no `env_prefix`), so deleting all of them
      needs no list either — and it is what keeps `AZURE_CLIENT_ID` away from
      `DefaultAzureCredential`, the one consumer that reads the environment itself.
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
    deployment actually applies rather than a second arrangement that resembles it."""
    from tc_runtime.migrate import upgrade_to_head

    from agent.runtime import MIGRATIONS

    upgrade_to_head(MIGRATIONS, sqlalchemy_url(postgres_url))
    return postgres_url


@pytest.fixture(scope="session")
async def seeded_prompt_revision_max_id(migrated_url: str) -> int:
    """Whatever id the migrations themselves left `prompt_revisions` on, captured once
    right after they ran — so a later migration seeding another revision needs no edit
    here, unlike a number written in by hand that this file has already had to bump once."""
    conn = await asyncpg.connect(asyncpg_dsn(migrated_url))
    try:
        return await conn.fetchval("SELECT max(id) FROM prompt_revisions")
    finally:
        await conn.close()


@pytest.fixture
async def db(
    migrated_url: str, seeded_prompt_revision_max_id: int
) -> AsyncIterator[asyncpg.Connection]:
    """A connection to the migrated database, with the tables emptied first.

    `prompt_revisions` is not in `TABLES`: unlike every other table here, the
    migrations themselves insert into it, and `migrated_url` runs them once for the
    whole session. Blindly truncating it would erase the seeds a test asserting on
    their actual text depends on. Everything up to `seeded_prompt_revision_max_id` is
    those seeds — the only things ever written to a table nothing else has touched yet
    — so dropping everything after it undoes whatever a previous test's own
    `create_prompt_revision` calls added, without reconstructing seeded text here a
    second time.
    """
    conn = await asyncpg.connect(asyncpg_dsn(migrated_url))
    try:
        await conn.execute(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE")
        await conn.execute(
            "DELETE FROM prompt_revisions WHERE id > $1", seeded_prompt_revision_max_id
        )
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

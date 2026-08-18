"""Shared fixtures — chiefly the throwaway PostgreSQL the `db` tests run against.

A container per test session rather than a shared development database, because the
schema is part of what is under test here. A table left behind by a previous run is
indistinguishable from a migration that works, and that is exactly the failure this
module cannot afford: the archive's correctness *is* its schema.

Docker is not assumed. Without it the `db` tests skip with a reason that says what to
start, instead of failing with a connection error that reads like a bug in the code.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import asyncpg
import pytest

from market_data.db import asyncpg_dsn, sqlalchemy_url

MODULE_ROOT = Path(__file__).resolve().parent.parent

# Testcontainers' reaper is a sidecar that bind-mounts the Docker socket so it can remove
# containers a hard-killed test run left behind. On Docker Desktop for macOS the socket
# lives under the user's home directory, which the VM refuses to mount, and every `db`
# test then fails on a container that will not start.
#
# Turning it off is safe here because the container fixture is a context manager: normal
# runs, failing runs and Ctrl-C all stop it on the way out. Only a SIGKILL of pytest
# leaks one, and `docker rm` on a stray `postgres:17-alpine` is the whole cleanup.
# Set the variable yourself to keep the reaper on a machine where it works.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

# Emptied between tests so that one test's rows are never another's premise. TRUNCATE
# rather than dropping and re-migrating: the schema is the same for every test, and
# re-running three migrations per test buys nothing.
TABLES = (
    "candles",
    "derived_candles",
    "tracked_pairs",
    "coverage_ranges",
    "collection_jobs",
    "collection_job_chunks",
    "pair_deletions",
)


# Generous, because Docker Desktop wakes its VM lazily and a first call after an idle
# spell can take several seconds. The earlier two-second budget was tight enough that a
# cold daemon read as an absent one, and thirty tests skipped on a machine where they
# would have passed — which is how they went unrun long enough to hide two real bugs.
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
    """Why the `db` tests cannot run here, or `None` to let them run.

    Only a machine with no Docker at all earns a skip. A daemon that is installed and
    failing does not: the tests are then left to run and fail with whatever the daemon
    actually said, because a silent skip on a machine that was supposed to have Docker
    is indistinguishable from a suite that passed.
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
    """The same database with the module's migrations applied.

    Applied by running alembic itself rather than by a hand-written CREATE TABLE in the
    fixture. A fixture that builds its own schema tests a schema no deployment will ever
    have, and the migration — the thing that has to work in production — goes unrun.

    Synchronous on purpose: alembic's async environment calls `asyncio.run`, which needs
    a thread with no loop already running. A sync fixture is such a thread; an async one
    is not.
    """
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

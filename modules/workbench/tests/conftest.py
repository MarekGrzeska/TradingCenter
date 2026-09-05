"""What every suite in this module needs, and what pytest will only take from here: three suites live under this
directory, and `pytest_addoption` is read from the *initial* conftest only, so `--run-live` would silently not exist."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from tc_runtime.db import sqlalchemy_url

from workbench.config import Settings

# See market_data's twin: the reaper's Docker-socket bind-mount fails on Docker Desktop for
# macOS, and the container fixtures already stop cleanly on their own.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

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
    return bool(os.environ.get("DOCKER_HOST")) or any(socket.exists() for socket in DOCKER_SOCKETS)


@pytest.fixture(autouse=True)
def _no_developer_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every source of settings a developer's machine has and CI does not: the module's `.env`, switched off at the class
    after a stale list cost six tests, and the process environment, which keeps `AZURE_CLIENT_ID` out of the credential."""
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)


# One container per chain rather than schemas in one, because each chain owns its `alembic_version`.
# They live here because the process under test needs all five: its lifespan migrates each before it serves.


@pytest.fixture(scope="session")
def agent_postgres_url() -> Iterator[str]:
    """A URL to an empty PostgreSQL, alive for the session and gone afterwards."""
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:17-alpine", driver=None) as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def teams_postgres_url() -> Iterator[str]:
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:17-alpine", driver=None) as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def polymarket_postgres_url() -> Iterator[str]:
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:17-alpine", driver=None) as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def polymarket_migrated_url(polymarket_postgres_url: str) -> str:
    from tc_runtime.migrate import upgrade_to_head

    from polymarket_data.runtime import MIGRATIONS

    upgrade_to_head(MIGRATIONS, sqlalchemy_url(polymarket_postgres_url))
    return polymarket_postgres_url


@pytest.fixture(scope="session")
def social_postgres_url() -> Iterator[str]:
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:17-alpine", driver=None) as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def social_migrated_url(social_postgres_url: str) -> str:
    from tc_runtime.migrate import upgrade_to_head

    from social_data.runtime import MIGRATIONS

    upgrade_to_head(MIGRATIONS, sqlalchemy_url(social_postgres_url))
    return social_postgres_url


@pytest.fixture(scope="session")
def strategy_postgres_url() -> Iterator[str]:
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:17-alpine", driver=None) as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def strategy_migrated_url(strategy_postgres_url: str) -> str:
    from tc_runtime.migrate import upgrade_to_head

    from strategy.runtime import MIGRATIONS

    upgrade_to_head(MIGRATIONS, sqlalchemy_url(strategy_postgres_url))
    return strategy_postgres_url


@pytest.fixture(scope="session")
def agent_migrated_url(agent_postgres_url: str) -> str:
    """The same database with the conversation's migrations applied — through the same function the process
    runs at startup, so the schema under test is the one a deployment actually applies."""
    from tc_runtime.migrate import upgrade_to_head

    from agent.runtime import MIGRATIONS

    upgrade_to_head(MIGRATIONS, sqlalchemy_url(agent_postgres_url))
    return agent_postgres_url


@pytest.fixture(scope="session")
def teams_migrated_url(teams_postgres_url: str) -> str:
    from tc_runtime.migrate import upgrade_to_head

    from teams.runtime import MIGRATIONS

    upgrade_to_head(MIGRATIONS, sqlalchemy_url(teams_postgres_url))
    return teams_postgres_url


# The catalogue every test that starts the process needs one of. Two entries so a test can
# assert on ordering, cheapest first.
WORKBENCH_MODELS = (
    '[{"id":"gpt-5.6-sol","model":"sol-prod","display_name":"Sol",'
    '"cost_rank":3,"input_rate_per_1m":"5","output_rate_per_1m":"30"},'
    '{"id":"gpt-5.6-luna","model":"luna-prod","display_name":"Luna",'
    '"cost_rank":1,"input_rate_per_1m":"1","output_rate_per_1m":"6"}]'
)


@pytest.fixture
def workbench_env(
    agent_migrated_url: str,
    teams_migrated_url: str,
    polymarket_migrated_url: str,
    social_migrated_url: str,
    strategy_migrated_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The smallest environment `workbench.app` will start in: everything the process refuses to start
    without and nothing else, so a test adding one is visibly adding it."""
    monkeypatch.setenv("AGENT_DATABASE_URL", agent_migrated_url)
    monkeypatch.setenv("TEAMS_DATABASE_URL", teams_migrated_url)
    monkeypatch.setenv("POLYMARKET_DATABASE_URL", polymarket_migrated_url)
    monkeypatch.setenv("SOCIAL_DATABASE_URL", social_migrated_url)
    monkeypatch.setenv("STRATEGY_DATABASE_URL", strategy_migrated_url)
    # The post archive's first pass runs the moment the process starts; pointed at a closed loopback port it
    # fails fast and logs, and no test here reaches a public feed.
    monkeypatch.setenv("SOCIAL_TRUTH_SOCIAL_FEED_URL", "http://127.0.0.1:9/feed")
    monkeypatch.setenv("AGENT_OPENAI_API_KEY", "key")
    monkeypatch.setenv("TEAMS_OPENAI_API_KEY", "another-key")
    monkeypatch.setenv("AGENT_MODELS", WORKBENCH_MODELS)
    monkeypatch.setenv("TEAMS_MODELS", WORKBENCH_MODELS)
    monkeypatch.setenv("AGENT_DEFAULT_MODEL_ID", "gpt-5.6-luna")

"""What this package supplies to shared plumbing, the refusals that keep it from starting misconfigured, and the absence
that is not one."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from strategies.config import Settings
from strategies.runtime import MIGRATION_LOCK_KEY, MIGRATIONS
from workbench.config import strategies_enabled


@pytest.fixture(autouse=True)
def _no_dotenv(tmp_path, monkeypatch):
    """`Settings` reads `.env` from the working directory, and a developer's own file must not decide a test."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("STRATEGIES_DATABASE_URL", raising=False)


def test_no_two_chains_in_this_process_share_a_lock_key() -> None:
    """A key silently shared would put two chains' migrations behind one lock, in databases neither can see."""
    import importlib

    # The archive keeps its key beside its database helpers, every other package in `runtime`.
    keys = {
        module: importlib.import_module(module).MIGRATION_LOCK_KEY
        for module in (
            "agent.runtime", "teams.runtime", "polymarket_data.runtime", "social_data.runtime", "market_data.db",
            "telegram_gateway.runtime", "youtube_data.runtime", "alerts.runtime", "strategies.runtime",
        )
    }

    assert len(set(keys.values())) == len(keys), keys
    assert keys["strategies.runtime"] == MIGRATION_LOCK_KEY


def test_migrations_live_beside_the_package() -> None:
    """The `Dockerfile` copies `strategies/` and `migrations/` as siblings, so an expression that resolves here has to
    resolve in the image too."""
    assert MIGRATIONS.name == "strategies"
    assert MIGRATIONS.parent.name == "migrations"
    assert (MIGRATIONS / "env.py").is_file()


def test_the_app_publishes_the_health_routes_the_platform_probes() -> None:
    from strategies.app import create_app

    assert {"/", "/health", "/ping"} <= set(create_app().openapi()["paths"])


def test_a_remote_database_without_an_identity_is_refused() -> None:
    with pytest.raises(ValidationError, match="loopback"):
        Settings(database_url="postgresql://db.example.com/strategies", _env_file=None)  # type: ignore[call-arg]


def test_without_a_database_the_package_is_not_part_of_the_process() -> None:
    assert strategies_enabled() is False


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_line_left_blank_is_the_line_not_being_there(monkeypatch, blank: str) -> None:
    monkeypatch.setenv("STRATEGIES_DATABASE_URL", blank)

    assert strategies_enabled() is False


def test_with_a_database_it_is(monkeypatch) -> None:
    monkeypatch.setenv("STRATEGIES_DATABASE_URL", "postgresql://strategies:pw@127.0.0.1:55432/strategies")

    assert strategies_enabled() is True


def test_settings_for_an_absent_package_are_refused_by_name() -> None:
    from workbench.config import Settings as ProcessSettings

    with pytest.raises(ValueError, match="STRATEGIES_DATABASE_URL is not set"):
        ProcessSettings.model_construct(strategies_database_url=None).for_strategies()


def test_the_browsers_that_read_the_archives_are_not_this_packages_callers() -> None:
    """The process's REST list holds the pocket, which reads archives; this package is the operator's research."""
    from workbench.config import Settings as ProcessSettings

    process = ProcessSettings.model_construct(
        strategies_database_url="postgresql://strategies:pw@127.0.0.1:55432/strategies",
        rest_caller_application_ids="pocket,terminal",
    )

    assert process.for_strategies().rest_caller_ids == frozenset()


async def test_a_configured_database_that_does_not_answer_stops_the_start_and_names_it(app) -> None:
    """Local mode, no identity: the refusal is the closed port itself, not a credential fetched on the way."""
    from strategies.app import serving

    unreachable = Settings(database_url="postgresql://strategies@127.0.0.1:1/strategies", _env_file=None)  # type: ignore[call-arg]

    with pytest.raises(RuntimeError, match="strategies database"):
        async with serving(app, unreachable):
            pass


@pytest.mark.db
async def test_the_package_migrates_an_empty_database_itself_and_then_answers(postgres_url, app, monkeypatch) -> None:
    """The pairing with `tc-runtime`'s migration, lock and schema check this package owns. The chain reads the process's
    settings, as every package's does in production, so the process's required lines are given placeholders."""
    import asyncpg
    import httpx
    from tc_runtime.db import asyncpg_dsn

    from strategies.app import serving

    admin = await asyncpg.connect(asyncpg_dsn(postgres_url))
    try:
        await admin.execute("DROP DATABASE IF EXISTS strategies_fresh")
        await admin.execute("CREATE DATABASE strategies_fresh")
    finally:
        await admin.close()
    fresh = postgres_url.rsplit("/", 1)[0] + "/strategies_fresh"
    placeholder = "postgresql://x:y@127.0.0.1:1/x"
    for name in ("AGENT", "TEAMS", "POLYMARKET", "SOCIAL", "MARKET", "TELEGRAM"):
        monkeypatch.setenv(f"{name}_DATABASE_URL", placeholder)
    for name in ("AGENT_OPENAI_API_KEY", "TEAMS_OPENAI_API_KEY", "AGENT_DEFAULT_MODEL_ID", "GATEWAY_API_KEY"):
        monkeypatch.setenv(name, "x")
    monkeypatch.setenv("STRATEGIES_DATABASE_URL", fresh)

    async with serving(app, Settings(database_url=fresh, _env_file=None)):  # type: ignore[call-arg]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
            response = await client.get("/health")
        async with app.state.pool.acquire() as conn:
            tables = {row["tablename"] for row in await conn.fetch("SELECT tablename FROM pg_tables")}

    assert response.json() == {"database": "reachable"}
    assert {"strategies", "strategy_revisions", "runs", "run_trades"} <= tables

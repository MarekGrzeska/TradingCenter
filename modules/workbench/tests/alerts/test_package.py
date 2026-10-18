"""What this package supplies to shared plumbing, the refusals that keep it from starting misconfigured, and the absence
that is not one."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from alerts.config import Settings
from alerts.runtime import MIGRATION_LOCK_KEY, MIGRATIONS
from workbench.config import alerts_enabled


@pytest.fixture(autouse=True)
def _no_dotenv(tmp_path, monkeypatch):
    """`Settings` reads `.env` from the working directory, and a developer's own file must not decide a test."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ALERTS_DATABASE_URL", raising=False)


def test_this_packages_lock_key_is_its_own() -> None:
    """A key silently shared would put two chains' migrations behind one lock, in databases neither can see."""
    assert MIGRATION_LOCK_KEY == 8120


def test_migrations_live_beside_the_package() -> None:
    """The `Dockerfile` copies `alerts/` and `migrations/` as siblings, so an expression that resolves here has to
    resolve in the image too."""
    assert MIGRATIONS.name == "alerts"
    assert MIGRATIONS.parent.name == "migrations"
    assert (MIGRATIONS / "env.py").is_file()


def test_the_app_publishes_the_health_routes_the_platform_probes() -> None:
    from alerts.app import create_app

    assert {"/", "/health", "/ping"} <= set(create_app().openapi()["paths"])


def test_a_remote_database_without_an_identity_is_refused() -> None:
    with pytest.raises(ValidationError, match="loopback"):
        Settings(database_url="postgresql://db.example.com/alerts", _env_file=None)


def test_an_identity_over_plaintext_is_refused() -> None:
    with pytest.raises(ValidationError, match="TLS"):
        Settings(database_url="postgresql://db.example.com/alerts", database_user="workbench", _env_file=None)


def test_without_a_database_the_package_is_not_part_of_the_process() -> None:
    assert alerts_enabled() is False


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_line_left_blank_is_the_line_not_being_there(monkeypatch, blank: str) -> None:
    monkeypatch.setenv("ALERTS_DATABASE_URL", blank)

    assert alerts_enabled() is False


def test_with_a_database_it_is(monkeypatch) -> None:
    monkeypatch.setenv("ALERTS_DATABASE_URL", "postgresql://alerts:pw@127.0.0.1:55432/alerts")

    assert alerts_enabled() is True


def test_settings_for_an_absent_package_are_refused_by_name() -> None:
    """A caller that skipped the question — the alembic chain run by hand on a `.env` without the line — hears which
    line, rather than what pydantic makes of it."""
    from workbench.config import Settings as ProcessSettings

    with pytest.raises(ValueError, match="ALERTS_DATABASE_URL is not set"):
        ProcessSettings.model_construct(alerts_database_url=None).for_alerts()


def test_the_browsers_that_read_the_archives_are_not_this_packages_callers() -> None:
    """The process's REST list holds the pocket, which reads; this package's REST decides who is told what, so its
    callers are its own line."""
    from workbench.config import Settings as ProcessSettings

    process = ProcessSettings.model_construct(
        alerts_database_url="postgresql://alerts:pw@127.0.0.1:55432/alerts",
        rest_caller_application_ids="pocket,terminal",
    )

    assert process.for_alerts().rest_caller_ids == frozenset()


def test_a_missing_model_key_is_a_supported_state_and_a_blank_one_is_a_missing_one() -> None:
    url = "postgresql://localhost:5432/alerts"
    assert Settings(database_url=url, _env_file=None).drafting is False
    assert Settings(database_url=url, openai_api_key="   ", _env_file=None).drafting is False
    assert Settings(database_url=url, openai_api_key="sk-test", _env_file=None).drafting is True

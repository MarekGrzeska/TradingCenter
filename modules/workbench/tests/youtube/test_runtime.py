"""The two facts this package supplies to shared plumbing, and the app it assembles."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from youtube_data.config import Settings
from youtube_data.runtime import MIGRATION_LOCK_KEY, MIGRATIONS


def test_this_packages_lock_key_is_its_own() -> None:
    """A key silently shared would put two chains' migrations behind one lock, in databases neither can see."""
    assert MIGRATION_LOCK_KEY == 8110


def test_migrations_live_beside_the_package() -> None:
    """The `Dockerfile` copies `youtube_data/` and `migrations/` as siblings, so an expression that resolves here has to
    resolve in the image too."""
    assert MIGRATIONS.name == "youtube"
    assert MIGRATIONS.parent.name == "migrations"
    assert (MIGRATIONS / "env.py").is_file()


def test_the_app_publishes_the_health_routes_the_platform_probes() -> None:
    """Read off the published document rather than off `app.routes`: the document is what a consumer sees, and what
    `caller_access.py`'s record is held against."""
    from youtube_data.app import create_app

    assert {"/", "/health", "/ping"} <= set(create_app().openapi()["paths"])


def test_a_remote_database_without_an_identity_is_refused() -> None:
    with pytest.raises(ValidationError, match="loopback"):
        Settings(database_url="postgresql://db.example.com/youtube", _env_file=None)


def test_an_identity_over_plaintext_is_refused() -> None:
    with pytest.raises(ValidationError, match="TLS"):
        Settings(
            database_url="postgresql://db.example.com/youtube",
            database_user="workbench",
            video_source="rss",
            transcript_providers="direct",
            analyser="openai",
            _env_file=None,
        )

"""The two facts this package supplies to shared plumbing, and the app it assembles."""

from __future__ import annotations

from social_data.runtime import MIGRATION_LOCK_KEY, MIGRATIONS


def test_this_packages_lock_key_is_still_its_own() -> None:
    """The key is an argument this package supplies, not a constant inside `tc-runtime`. A key silently
    shared would put two chains' migrations behind one lock, in databases neither can see."""
    assert MIGRATION_LOCK_KEY == 8090


def test_migrations_live_beside_the_package() -> None:
    """The workbench's `Dockerfile` copies `social_data/` and `migrations/` as siblings, so an expression
    that resolves here has to resolve in the image too — this chain is one of that directory's
    subdirectories, beside the conversation's, the teams' and the prediction-market archive's."""
    assert MIGRATIONS.name == "social"
    assert MIGRATIONS.parent.name == "migrations"
    assert (MIGRATIONS / "env.py").is_file()


def test_the_app_publishes_the_health_routes_the_platform_probes() -> None:
    """`/` names the package, and `/ping` answers a constant. Read off the published document rather than off
    `app.routes`: the document is what a consumer sees, and what `caller_access.py`'s record is held against."""
    from social_data.app import create_app

    paths = set(create_app().openapi()["paths"])
    assert {"/", "/health", "/ping"} <= paths

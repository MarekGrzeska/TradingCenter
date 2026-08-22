"""The two facts this module supplies to shared plumbing, and the app it assembles."""

from __future__ import annotations

from polymarket_data.runtime import MIGRATION_LOCK_KEY, MIGRATIONS


def test_this_modules_lock_key_is_still_its_own() -> None:
    """The key is an argument this module supplies to `tc_runtime.db.advisory_lock`, not a
    constant inside it. That is the whole risk of sharing the plumbing: a key silently
    changed — or silently shared with market-data's 8020 or the workbench's 8030/8050 —
    would put two modules' migrations behind one lock, in databases neither can see, and
    the symptom would be a start-up that hangs with no failing query to find it by.
    """
    assert MIGRATION_LOCK_KEY == 8070


def test_migrations_live_beside_the_package() -> None:
    """`Dockerfile` copies `polymarket_data/` and `migrations/` as siblings, so an
    expression that resolves here has to resolve in the image too."""
    assert MIGRATIONS.name == "migrations"
    assert (MIGRATIONS / "env.py").is_file()


def test_the_app_publishes_the_health_routes_the_platform_probes() -> None:
    """`/` is what `scripts/deploy_probe.py` reads to tell this module from another one on
    the same plan, and `/ping` is the one path Easy Auth may exempt — it answers a
    constant, so its answer cannot vary with anything the archive holds."""
    from polymarket_data.app import create_app

    # Read off the published document rather than off `app.routes`: the document is what a
    # consumer actually sees, and it is what `caller_access.py`'s record will be held
    # against once there is one.
    paths = set(create_app().openapi()["paths"])
    assert {"/", "/health", "/ping"} <= paths

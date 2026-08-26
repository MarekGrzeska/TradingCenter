"""The two facts the shared runtime cannot know about this module."""

from __future__ import annotations

from strategy.runtime import MIGRATION_LOCK_KEY, MIGRATIONS


def test_the_lock_key_is_this_modules_own() -> None:
    """8080, following the convention the others set. Asserted as a number rather than described in a comment: the
    keys are only meaningful while they are distinct, and a collision is a start-up that hangs rather than fails."""
    assert MIGRATION_LOCK_KEY == 8080


def test_the_migrations_are_beside_the_package() -> None:
    """`strategy/` and `migrations/` are siblings in the repository and in the image, so one expression locates them
    in both. A wrong path here is a module that starts against an empty database and reports success."""
    assert MIGRATIONS.is_dir()
    assert (MIGRATIONS / "env.py").is_file()
    assert (MIGRATIONS / "versions").is_dir()

"""The startup check that ties an image to the schema it was written against."""

from __future__ import annotations

import asyncpg
import pytest

from agent.schema_version import SchemaMismatch, applied_heads, expected_heads, verify


class FakeConnection:
    """Enough of a connection for the one statement `schema_version.py` runs."""

    def __init__(self, versions: list[str] | None) -> None:
        self._versions = versions

    async def fetch(self, query: str) -> list[dict[str, str]]:
        if self._versions is None:
            raise asyncpg.UndefinedTableError('relation "alembic_version" does not exist')
        return [{"version_num": version} for version in self._versions]


def test_the_expected_head_is_read_from_the_migrations_beside_the_package() -> None:
    # Not asserted against a literal revision id: that would have to be edited by every
    # migration, and the thing worth proving is that the directory is found at all.
    assert len(expected_heads()) == 1


async def test_a_database_at_the_expected_head_starts() -> None:
    head = next(iter(expected_heads()))

    await verify(FakeConnection([head]))  # type: ignore[arg-type]


async def test_a_database_one_migration_behind_refuses_to_start() -> None:
    # `0002` is where production actually sat while an image carrying `0003` served
    # `500` from `GET /prompt` — the case this whole file exists for.
    with pytest.raises(SchemaMismatch) as err:
        await verify(FakeConnection(["0002"]))  # type: ignore[arg-type]

    # The operator reads this in a container log with no other context, so it has to name
    # both revisions. It no longer names a command to run: the module migrates itself
    # before reaching here (`migrate.py`), so reaching here at all means the upgrade did
    # not arrive where it reported — running it again by hand is not the answer.
    assert "0002" in str(err.value)
    assert next(iter(expected_heads())) in str(err.value)


async def test_a_database_ahead_of_the_image_refuses_too() -> None:
    with pytest.raises(SchemaMismatch):
        await verify(FakeConnection(["9999_from_a_newer_image"]))  # type: ignore[arg-type]


async def test_a_database_that_was_never_migrated_says_so() -> None:
    with pytest.raises(SchemaMismatch) as err:
        await verify(FakeConnection(None))  # type: ignore[arg-type]

    assert "never migrated" in str(err.value)


async def test_a_missing_version_table_reads_as_no_revision_rather_than_an_error() -> None:
    assert await applied_heads(FakeConnection(None)) == set()  # type: ignore[arg-type]


@pytest.mark.db
async def test_the_migrated_database_the_tests_run_against_passes(db: asyncpg.Connection) -> None:
    # The fixture applies the migrations with alembic itself, so this is the real pairing
    # a deployment has: this image's `migrations/` against a database they were run on.
    await verify(db)

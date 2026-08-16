"""The startup check that ties an image to the schema it was written against."""

from __future__ import annotations

import asyncpg
import pytest

from teams.schema_version import SchemaMismatch, applied_heads, expected_heads, verify


class FakeConnection:
    """Enough of a connection for the one statement `schema_version.py` runs."""

    def __init__(self, versions: list[str] | None) -> None:
        self._versions = versions

    async def fetch(self, query: str) -> list[dict[str, str]]:
        if self._versions is None:
            raise asyncpg.UndefinedTableError('relation "alembic_version" does not exist')
        return [{"version_num": version} for version in self._versions]


def test_expected_heads_is_empty_before_any_migration_exists() -> None:
    # Not a broken state: zero migrations is a valid "at head" the same way a directory
    # with nothing in it has nothing missing from it. The next change adds the first
    # revision, and this assertion is what will need to change alongside it.
    assert expected_heads() == set()


async def test_a_never_migrated_database_matches_the_still_empty_expectation() -> None:
    # `applied_heads` reads "no revision at all" the same way whether the table is
    # missing or the image expects nothing — the two are indistinguishable and both
    # correct here, since nothing has been migrated on either side yet.
    await verify(FakeConnection(None))  # type: ignore[arg-type]


async def test_a_database_carrying_a_revision_this_image_does_not_know_refuses() -> None:
    # The case that will matter once a migration exists: a database ahead of the image,
    # here simulated as a database carrying anything at all while the image expects
    # nothing.
    with pytest.raises(SchemaMismatch) as err:
        await verify(FakeConnection(["9999_from_a_newer_image"]))  # type: ignore[arg-type]

    assert "9999_from_a_newer_image" in str(err.value)


async def test_a_missing_version_table_reads_as_no_revision_rather_than_an_error() -> None:
    assert await applied_heads(FakeConnection(None)) == set()  # type: ignore[arg-type]


@pytest.mark.db
async def test_the_migrated_database_the_tests_run_against_passes(db: asyncpg.Connection) -> None:
    # The fixture applies the migrations with alembic itself, so this is the real pairing
    # a deployment has: this image's `migrations/` against a database they were run on —
    # today, both sides empty.
    await verify(db)

"""The comparison every module makes before it serves anything.

The interesting case here is the one that decided *which* of the two copies became the
package: a module whose image ships no revision at all. Agent's version formatted the
expected set unguarded and produced "expects the database at , and it is at …" — a
sentence with a hole where the answer should be. Teams' version named the case. Neither
module had a test for it, which is how the fix sat in one copy for a week.
"""

from __future__ import annotations

import pytest

from tc_runtime.schema_version import SchemaMismatch, verify


class FakeConnection:
    """Answers the one query `applied_heads` runs. `None` stands for a database that has
    never been migrated — the table does not exist yet."""

    def __init__(self, heads: list[str] | None) -> None:
        self._heads = heads

    async def fetch(self, query: str):
        del query
        if self._heads is None:
            import asyncpg

            raise asyncpg.UndefinedTableError("relation alembic_version does not exist")
        return [{"version_num": head} for head in self._heads]


async def test_an_image_shipping_no_revision_says_so_rather_than_leaving_a_gap(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("tc_runtime.schema_version.expected_heads", lambda _migrations: set())

    with pytest.raises(SchemaMismatch) as err:
        await verify(FakeConnection(["0007"]), tmp_path)  # type: ignore[arg-type]

    message = str(err.value)
    assert "no revision (none exist yet)" in message
    assert "at , and" not in message, "the sentence must not stop where the answer goes"


async def test_a_database_that_was_never_migrated_says_so(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("tc_runtime.schema_version.expected_heads", lambda _migrations: {"0007"})

    with pytest.raises(SchemaMismatch) as err:
        await verify(FakeConnection(None), tmp_path)  # type: ignore[arg-type]

    assert "never migrated" in str(err.value)


async def test_a_database_at_the_expected_head_passes(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("tc_runtime.schema_version.expected_heads", lambda _migrations: {"0007"})

    await verify(FakeConnection(["0007"]), tmp_path)  # type: ignore[arg-type]


async def test_a_database_ahead_of_the_image_refuses_too(tmp_path, monkeypatch) -> None:
    """Not "at least" — a rollback that left the schema forward is the same accident from
    the other side, and the code running against it is as untested."""
    monkeypatch.setattr("tc_runtime.schema_version.expected_heads", lambda _migrations: {"0007"})

    with pytest.raises(SchemaMismatch):
        await verify(FakeConnection(["9999_from_a_newer_image"]), tmp_path)  # type: ignore[arg-type]

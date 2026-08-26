"""The rule that a deployment's seed yields to a person, and the bug it was written from: migrations seed each version
one higher and `_next_prompt_version` does the same `+1`, so the seed used to win the read after one save."""

from __future__ import annotations

import asyncpg
import pytest

from agent import store
from agent.prompt_seed import _SEED, seed_prompt
from agent.store.prompt import _next_prompt_version

pytestmark = pytest.mark.db


async def _seed(db: asyncpg.Connection, version: str, text: str = "seeded") -> None:
    """Run the migrations' own seed statement, against the connection the fixture gives. Derived from
    `_SEED` rather than retyped: a copy would let the rule under test drift from the rule the migrations run."""
    sql = str(_SEED)
    for n, name in enumerate(("version", "with_tools", "without_tools"), start=1):
        sql = sql.replace(f":{name}", f"${n}")
    await db.execute(sql, version, text, text)


class TestTheSeedYields:
    async def test_a_seed_lands_when_the_newest_revision_is_itself_a_seed(
        self, db: asyncpg.Connection
    ) -> None:
        """The ordinary deployment: nobody has edited, so the better prompt arrives."""
        await _seed(db, "v99", "the deployment's text")

        latest = await store.latest_prompt_revision(db)
        assert latest.version == "v99"
        assert latest.with_tools_body == "the deployment's text"
        assert latest.source == "seed"

    async def test_a_seed_does_not_land_after_the_operator_has_written(
        self, db: asyncpg.Connection
    ) -> None:
        """The failure mode this guard exists for."""
        mine = await store.create_prompt_revision(
            db, with_tools_body="what I wrote", without_tools_body="what I wrote"
        )

        await _seed(db, "v99", "the deployment's text")

        latest = await store.latest_prompt_revision(db)
        assert latest.version == mine.version
        assert latest.with_tools_body == "what I wrote"
        assert latest.source == "operator"

    async def test_the_operators_save_is_marked_as_theirs(self, db: asyncpg.Connection) -> None:
        saved = await store.create_prompt_revision(
            db, with_tools_body="mine", without_tools_body="mine"
        )
        assert saved.source == "operator"

    async def test_one_operator_write_does_not_block_the_deployment_forever(
        self, db: asyncpg.Connection
    ) -> None:
        """A seed refused once must not mean the table is closed to seeds for good. It reopens the moment
        the newest row is a seed again, so this is really a statement about the rule having no latch."""
        await store.create_prompt_revision(db, with_tools_body="mine", without_tools_body="mine")
        await _seed(db, "v99")
        assert (await store.latest_prompt_revision(db)).source == "operator"

        # The row a future change might add deliberately — an operator accepting the new
        # default — puts a seed back on top, and seeding works again.
        await db.execute(
            "INSERT INTO prompt_revisions (version, with_tools_body, without_tools_body, source)"
            " VALUES ('v100', 'accepted', 'accepted', 'seed')"
        )
        await _seed(db, "v101", "the next deployment")

        assert (await store.latest_prompt_revision(db)).version == "v101"


class TestVersionsAreUnique:
    async def test_two_rows_may_not_share_a_version(self, db: asyncpg.Connection) -> None:
        """Before this, `downgrade()` of a seeding migration would have deleted both."""
        await db.execute(
            "INSERT INTO prompt_revisions (version, with_tools_body, without_tools_body, source)"
            " VALUES ('v99', 'first', 'first', 'operator')"
        )

        with pytest.raises(asyncpg.UniqueViolationError):
            await db.execute(
                "INSERT INTO prompt_revisions (version, with_tools_body, without_tools_body,"
                " source) VALUES ('v99', 'second', 'second', 'seed')"
            )

    async def test_source_accepts_only_the_two_writers(self, db: asyncpg.Connection) -> None:
        with pytest.raises(asyncpg.CheckViolationError):
            await db.execute(
                "INSERT INTO prompt_revisions (version, with_tools_body, without_tools_body,"
                " source) VALUES ('v99', 'x', 'x', 'somebody-else')"
            )


async def test_the_operators_next_version_is_the_one_the_next_seed_would_use(
    db: asyncpg.Connection,
) -> None:
    """The arithmetic behind the whole bug, kept as a statement rather than a memory. Not a defect to fix in
    `_next_prompt_version` — it is why the guard cannot be replaced by "seed a version nobody has taken"."""
    at_head = await store.latest_prompt_revision(db)
    number = int(at_head.version.removeprefix("v"))

    assert _next_prompt_version(at_head.version) == f"v{number + 1}"


def test_the_helper_a_migration_calls_runs_the_statement_under_test() -> None:
    """`seed_prompt` must execute `_SEED` — the text every test above runs."""
    import inspect

    assert "_SEED" in inspect.getsource(seed_prompt)

    sql = " ".join(str(_SEED).split())
    assert "WHERE NOT EXISTS (SELECT 1 FROM prompt_revisions)" in sql
    assert "OR (SELECT source FROM prompt_revisions ORDER BY id DESC LIMIT 1) = 'seed'" in sql
    assert "'seed'" in sql


def test_seed_prompt_is_not_reachable_from_the_runtime_path() -> None:
    """It is migration-time code. A caller in a router or a tool would be seeding a
    prompt on a request, which is not a thing this module does."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2] / "agent"
    callers = [
        path
        for path in root.rglob("*.py")
        if path.name != "prompt_seed.py"
        and "prompt_seed import" in path.read_text(encoding="utf-8")
    ]

    assert callers == [], f"prompt_seed reached from {[str(p) for p in callers]}"


def test_the_migration_that_added_source_states_the_versions_it_backfills() -> None:
    """The seeded versions are literals in `0013`, not read from those migrations: a backfill that reads
    today's constants answers a different question every time it is replayed."""
    import pathlib

    migration = (
        pathlib.Path(__file__).resolve().parents[2]
        / "migrations/agent/versions/0013_prompt_seed_yields_to_operator.py"
    ).read_text(encoding="utf-8")

    assert '_SEEDED_VERSIONS = ("v4", "v5", "v6", "v7", "v8", "v9", "v10", "v11")' in migration
    code = "\n".join(
        line for line in migration.splitlines() if not line.lstrip().startswith("#")
    )
    assert "_SEED_VERSION" not in code, "the backfill must not read the seeds' own constants"


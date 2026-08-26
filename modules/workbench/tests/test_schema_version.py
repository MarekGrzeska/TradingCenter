"""The one thing about `schema_version` that is this module's rather than the library's. Both surfaces used
to carry a near-identical copy of the library's own unit tests; those live with the code they test.

What is left is the pairing no library can check: this image's migrations against a database they were run
on, once per schema — and that the two schemas take different advisory locks."""

from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest
from tc_runtime.db import asyncpg_dsn
from tc_runtime.schema_version import verify

from agent.runtime import MIGRATION_LOCK_KEY as AGENT_LOCK_KEY
from agent.runtime import MIGRATIONS as AGENT_MIGRATIONS
from teams.runtime import MIGRATION_LOCK_KEY as TEAMS_LOCK_KEY
from teams.runtime import MIGRATIONS as TEAMS_MIGRATIONS


@pytest.fixture(params=["agent", "teams"])
def migrated_schema(
    request: pytest.FixtureRequest, agent_migrated_url: str, teams_migrated_url: str
) -> tuple[str, Path]:
    """Both URLs are requested as arguments rather than pulled with `getfixturevalue`:
    the migration runs through `asyncio.run`, which refuses to start inside the loop an
    async test body is already on."""
    if request.param == "agent":
        return agent_migrated_url, AGENT_MIGRATIONS
    return teams_migrated_url, TEAMS_MIGRATIONS


@pytest.mark.db
async def test_the_migrated_database_the_tests_run_against_passes(
    migrated_schema: tuple[str, Path],
) -> None:
    # The fixture applies the migrations with alembic itself, so this is the real pairing a
    # deployment has: this image's `migrations/` against a database they were run on.
    url, migrations = migrated_schema
    conn = await asyncpg.connect(asyncpg_dsn(url))
    try:
        await verify(conn, migrations)
    finally:
        await conn.close()


def test_the_two_schemas_do_not_share_an_advisory_lock() -> None:
    """The key stopped being a constant in the file that takes the lock and became an argument each surface
    supplies. One key silently equal to the other would put two chains behind one lock, in databases neither
    can see. The conversation's own number is pinned next door; what is here is the pair."""
    assert TEAMS_LOCK_KEY == 8050
    assert AGENT_LOCK_KEY != TEAMS_LOCK_KEY

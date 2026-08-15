"""Whether the database this process reached is at the revision its code was built for.

A twin of `market_data/schema_version.py`, duplicated rather than shared — no library
between modules — and it is here for the second time the same gap cost something. The
container never migrates (`Dockerfile`), and `deploy-agent.yml` never migrates either,
so until this file nothing tied an image to a schema. On 15 August that showed: the
image carrying `0003_prompt_revisions` was serving against a database still at `0002`,
and `GET /prompt` answered `500` from a table that did not exist while everything else
in the module worked. A half-broken deployment with no symptom until an operator opens
the one panel that reads the new table.

This is the tie, and it is a comparison rather than a migration: the heads alembic ships
in the image against the version the database says it is at. A process that finds them
apart refuses to start — the whole module goes dark and says why in its own log, instead
of one route failing quietly.

Worth knowing what this does *not* buy here, because market-data's twin does buy it:
`deploy-agent.yml`'s check reads the App Service control plane (site state, image tag),
not the container, so a deploy landing on an unmigrated database still reports green.
The agent has no path excluded from Easy Auth to probe the way market-data's `/ws/candles`
is probed. What changes is the failure: total and logged at startup, rather than partial
and silent.
"""

from __future__ import annotations

import logging
from pathlib import Path

import asyncpg
from alembic.config import Config
from alembic.script import ScriptDirectory

log = logging.getLogger(__name__)

# `agent/` and `migrations/` are siblings — in the repository and in the image
# (`Dockerfile` copies both to `/app`), so one expression locates it in both.
_MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


class SchemaMismatch(RuntimeError):
    """The database is not at the revision this code expects."""


def expected_heads() -> set[str]:
    """The revisions this image's migrations end at.

    A `Config` built in memory rather than from `alembic.ini`: the file's `script_location`
    is relative, so reading it would resolve against the working directory, and the
    process that needs this answer runs from wherever App Service started it.
    """
    config = Config()
    config.set_main_option("script_location", str(_MIGRATIONS))
    return set(ScriptDirectory.from_config(config).get_heads())


async def applied_heads(conn: asyncpg.Connection) -> set[str]:
    """What the database says it is at. Empty if it has never been migrated at all."""
    try:
        rows = await conn.fetch("SELECT version_num FROM alembic_version")
    except asyncpg.UndefinedTableError:
        return set()
    return {row["version_num"] for row in rows}


async def verify(conn: asyncpg.Connection) -> None:
    """Raise unless the database is at the revision this code was built for.

    Deliberately not "at least" — a database ahead of the image is the same accident seen
    from the other side (a rollback that left the schema where it was), and the code
    running against it is as untested as the case above.
    """
    expected = expected_heads()
    applied = await applied_heads(conn)
    if applied == expected:
        log.info("database schema is at %s", ", ".join(sorted(expected)))
        return

    at = ", ".join(sorted(applied)) if applied else "no revision at all (never migrated)"
    raise SchemaMismatch(
        f"this image expects the database at {', '.join(sorted(expected))}, and it is at "
        f"{at}. Nothing has been migrated automatically and nothing will be — run "
        f"`alembic upgrade head` against this database, then start the module again."
    )

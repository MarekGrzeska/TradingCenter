"""Whether the database this process reached is at the revision its code was built for.

Named for the revision rather than the schema because `tests/test_schema.py` already owns
that word for a different question — what the migrations build, checked against a database
they were run on. This module reads one row and compares it with one number.


The container never migrates — that decision is in the `Dockerfile` and it is the right
one — so nothing else ties an image to a schema. On 10 August that gap was the whole
outage: a deploy carrying migration `0007` reported success against a database still at
`0006`, and four routes answered `500` for thirty-five minutes while the deploy sat green.

This is the tie, and it is a comparison rather than a migration: the heads alembic ships
in the image against the version the database says it is at. A process that finds them
apart refuses to start, which turns a silent half-broken deployment into a failed one —
the smoke check in `deploy-market-data.yml` cannot reach a container that never serves.
"""

from __future__ import annotations

import logging
from pathlib import Path

import asyncpg
from alembic.config import Config
from alembic.script import ScriptDirectory

log = logging.getLogger(__name__)

# `market_data/` and `migrations/` are siblings — in the repository and in the image
# (`Dockerfile` copies both to `/app`), so one expression locates it in both.
_MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


class SchemaMismatch(RuntimeError):
    """The database is not at the revision this code expects."""


def expected_heads() -> set[str]:
    """The revisions this image's migrations end at.

    A `Config` built in memory rather than from `alembic.ini`: the file's `script_location`
    is relative, so reading it would resolve against the working directory, and the
    process that needs this answer runs from wherever App Service started it. The rest of
    the file — logging, the file template — has nothing to say about which revision is
    last.
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

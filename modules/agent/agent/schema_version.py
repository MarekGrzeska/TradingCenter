"""Whether the database this process reached is at the revision its code was built for.

A twin of `market_data/schema_version.py`, duplicated rather than shared — no library
between modules. A comparison, never a migration: the heads alembic ships in the image
against the version the database says it is at.

`migrate.py` runs immediately before this, so the common case is that this check passes
over a database it just watched being migrated. What it still catches is the pair the
migration cannot fix:

- **database behind the image after migrating** — the upgrade reported success and did
  not arrive where it said it would;
- **database ahead of the image** — an older image was deployed onto a newer schema.
  This one gets *more* likely once deployments migrate on their own, not less, because
  the schema now moves forward at every deploy and a rollback moves only the code back.

Both leave the module running code against a schema it was never tested on, so both end
the same way: the process refuses to start and says which two revisions disagree.

Written after 15 August, when the image carrying `0003_prompt_revisions` served against a
database still at `0002` and only `GET /prompt` failed — a half-broken deployment with no
symptom until an operator opened the one panel that read the new table.
"""

from __future__ import annotations

import logging

import asyncpg
from alembic.script import ScriptDirectory

from .migrate import alembic_config

log = logging.getLogger(__name__)


class SchemaMismatch(RuntimeError):
    """The database is not at the revision this code expects."""


def expected_heads() -> set[str]:
    """The revisions this image's migrations end at."""
    return set(ScriptDirectory.from_config(alembic_config()).get_heads())


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
        f"{at} — after this process already ran its migrations. Either the upgrade did "
        f"not arrive where it reported, or this image is older than the schema, in which "
        f"case the deployment went backwards and only the code came with it."
    )

"""Whether the database a process reached is at the revision its code was built for — a comparison, never
a migration. It catches the pair a migration cannot fix: a database behind the image after migrating, and
one ahead of it after a rollback. Written after 15 August 2026, when only `GET /prompt` failed."""

from __future__ import annotations

import logging
from pathlib import Path

import asyncpg
from alembic.script import ScriptDirectory

from .migrate import alembic_config

log = logging.getLogger(__name__)


class SchemaMismatch(RuntimeError):
    """The database is not at the revision this code expects."""


def expected_heads(migrations: Path) -> set[str]:
    """The revisions this image's migrations end at."""
    return set(ScriptDirectory.from_config(alembic_config(migrations)).get_heads())


async def applied_heads(conn: asyncpg.Connection) -> set[str]:
    """What the database says it is at. Empty if it has never been migrated at all."""
    try:
        rows = await conn.fetch("SELECT version_num FROM alembic_version")
    except asyncpg.UndefinedTableError:
        return set()
    return {row["version_num"] for row in rows}


async def verify(conn: asyncpg.Connection, migrations: Path) -> None:
    """Raise unless the database is at the revision this code was built for. Deliberately not "at least":
    a database ahead of the image is the same accident from the other side."""
    expected = expected_heads(migrations)
    applied = await applied_heads(conn)
    if applied == expected:
        at = ", ".join(sorted(expected)) if expected else "no revision (none exist yet)"
        log.info("database schema is at %s", at)
        return

    at = ", ".join(sorted(applied)) if applied else "no revision at all (never migrated)"
    expected_text = ", ".join(sorted(expected)) if expected else "no revision (none exist yet)"
    raise SchemaMismatch(
        f"this image expects the database at {expected_text}, and it is at {at} — after "
        f"this process already ran its migrations. Either the upgrade did not arrive "
        f"where it reported, or this image is older than the schema, in which case the "
        f"deployment went backwards and only the code came with it."
    )

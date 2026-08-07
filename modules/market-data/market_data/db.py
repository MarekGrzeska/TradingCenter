"""The connection string, in the two shapes this module needs it.

`DATABASE_URL` is written driver-neutral — `postgresql://user:pass@host/db` — because it
is an operator-facing setting and an operator should not have to know which Python
library reaches the database. Inside, two libraries do, and they disagree about the
scheme:

    asyncpg      wants a plain `postgresql://` and chokes on a `+driver` suffix
    SQLAlchemy   wants `postgresql+asyncpg://`, or it reaches for a sync driver
                 that is not installed

Both translations live here so neither becomes a rule someone has to remember at every
call site.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg

_SCHEME_SEPARATOR = "://"


def asyncpg_dsn(database_url: str) -> str:
    """The URL as asyncpg takes it: scheme without a driver suffix."""
    scheme, separator, rest = database_url.partition(_SCHEME_SEPARATOR)
    if not separator:
        raise ValueError(f"DATABASE_URL is not a usable connection string: {database_url!r}")
    return f"{scheme.split('+', 1)[0]}{_SCHEME_SEPARATOR}{rest}"


def sqlalchemy_url(database_url: str) -> str:
    """The URL as SQLAlchemy takes it — asyncpg named, because it is the only driver here.

    Alembic runs through SQLAlchemy; without the suffix it defaults to psycopg2, which
    this module does not install, and the failure reads like a missing database rather
    than a missing driver.
    """
    scheme, separator, rest = database_url.partition(_SCHEME_SEPARATOR)
    if not separator:
        raise ValueError(f"DATABASE_URL is not a usable connection string: {database_url!r}")
    return f"{scheme.split('+', 1)[0]}+asyncpg{_SCHEME_SEPARATOR}{rest}"


@asynccontextmanager
async def connect(database_url: str) -> AsyncIterator[asyncpg.Connection]:
    """One connection, closed on the way out."""
    conn = await asyncpg.connect(asyncpg_dsn(database_url))
    try:
        yield conn
    finally:
        await conn.close()

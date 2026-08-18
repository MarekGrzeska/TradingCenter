"""The connection string, the pool and the migration lock — in the shapes every module
with a database needs them.

One copy, taken from `agent/db.py` on 18 August 2026, where it was 97.1% identical to
`teams/db.py`. What did *not* come here is `market_data/db.py`: measured at 56.2% against
this one, with its own thirty-minute migration window for the largest table in the
repository. That is a different file, not a copy that drifted, and it stays where it is
(`packages-replace-the-hand-copies/design.md`, D4).

What this package cannot know stays with the caller: which advisory-lock key a module's
migrations take, and where its migrations live. Both arrive as arguments.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import asyncpg
import asyncpg.pool
from azure.identity.aio import ClientSecretCredential, DefaultAzureCredential

log = logging.getLogger(__name__)

# What a `store.py` function actually receives: `pool.acquire()` yields a
# `PoolConnectionProxy`, not a `Connection` — it forwards every method at runtime
# (`__getattr__`) but does not subclass `Connection`, so a bare `asyncpg.Connection`
# annotation on a store function rejects the one thing every route actually passes it.
Conn = asyncpg.Connection | asyncpg.pool.PoolConnectionProxy

_SCHEME_SEPARATOR = "://"

# Azure Database for PostgreSQL's own resource id — the audience every Entra token
# presented to it must be issued for.
_AAD_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"

Credential = ClientSecretCredential | DefaultAzureCredential


class LockNotAcquired(RuntimeError):
    """The lock did not free up within the wait the caller allows."""


@asynccontextmanager
async def advisory_lock(
    conn: Conn, key: int, *, wait: float, poll: float = 1.0
) -> AsyncIterator[None]:
    """Holds a session-level advisory lock on `conn`, or refuses.

    `pg_try_advisory_lock` in a loop rather than the blocking `pg_advisory_lock`, because
    the blocking form has nowhere to put a deadline: it returns when it returns. A wait
    with no end is how a module that will never start looks exactly like one that is
    starting slowly.

    A lock left behind by a process that died needs no timeout to clear — it is session
    scoped, so Postgres drops it with the connection. `wait` is therefore sized for the
    slow case (a long migration ahead of us in the queue), not the dead one.

    `key` is the caller's, and it matters that it stays the caller's: advisory locks are
    scoped to a database, so two modules sharing a value would each be waiting on a lock
    the other holds in a database it cannot see. Every module asserts its own value in
    its own test suite.
    """
    deadline = time.monotonic() + wait
    while not await conn.fetchval("SELECT pg_try_advisory_lock($1)", key):
        if time.monotonic() >= deadline:
            raise LockNotAcquired(
                f"another process has held the migration lock ({key}) for longer than "
                f"{wait:.0f}s. It is either still migrating or its connection is still "
                f"open; this process will not migrate behind it."
            )
        await asyncio.sleep(poll)
    try:
        yield
    finally:
        # Unlocks on the same connection that locked — a session lock belongs to its
        # session, and this one is held open for exactly that reason.
        await conn.fetchval("SELECT pg_advisory_unlock($1)", key)


def asyncpg_dsn(database_url: str) -> str:
    """The URL as asyncpg takes it: scheme without a driver suffix."""
    scheme, separator, rest = database_url.partition(_SCHEME_SEPARATOR)
    if not separator:
        raise ValueError(f"DATABASE_URL is not a usable connection string: {database_url!r}")
    return f"{scheme.split('+', 1)[0]}{_SCHEME_SEPARATOR}{rest}"


def sqlalchemy_url(database_url: str) -> str:
    """The URL as SQLAlchemy takes it — asyncpg named, because it is the only driver
    here. Alembic runs through SQLAlchemy; without the suffix it defaults to psycopg2,
    which no module here installs."""
    scheme, separator, rest = database_url.partition(_SCHEME_SEPARATOR)
    if not separator:
        raise ValueError(f"DATABASE_URL is not a usable connection string: {database_url!r}")
    return f"{scheme.split('+', 1)[0]}+asyncpg{_SCHEME_SEPARATOR}{rest}"


def _connection_target(database_url: str) -> str:
    """`host:port/dbname` — never a credential — for logging a connection failure."""
    parsed = urlparse(asyncpg_dsn(database_url))
    return f"{parsed.hostname}:{parsed.port or 5432}{parsed.path}"


def _credential(
    client_id: str | None, client_secret: str | None, tenant_id: str | None
) -> Credential:
    """All three present selects a service principal — local development's own
    identity. None of them present falls through to `DefaultAzureCredential`, which in
    Azure finds the App Service's system-assigned managed identity with no
    configuration at all. A partial set authenticates as nothing and is rejected."""
    values = (("client_id", client_id), ("client_secret", client_secret), ("tenant_id", tenant_id))
    given = [name for name, value in values if value]
    if given and len(given) < 3:
        raise ValueError(
            "client_id, client_secret and tenant_id must be given together or not at "
            f"all — only {given} were set, which authenticates as nothing."
        )
    if client_id and client_secret and tenant_id:
        return ClientSecretCredential(tenant_id, client_id, client_secret)
    return DefaultAzureCredential()


class _TokenProvider:
    """Fetches an Entra token on every call — once per physical connection asyncpg
    opens, which is what makes a connection opened after the previous token expired
    just work, with no separate refresh loop to get wrong."""

    def __init__(self, credential: Credential) -> None:
        self._credential = credential

    async def __call__(self) -> str:
        try:
            token = await self._credential.get_token(_AAD_SCOPE)
        except Exception as err:
            raise RuntimeError(f"could not obtain a database credential: {err}") from err
        return token.token


def identity_connect_args(
    user: str,
    client_id: str | None,
    client_secret: str | None,
    tenant_id: str | None,
) -> tuple[dict[str, object], Credential]:
    """`connect_args` for a SQLAlchemy engine reaching this database with identity auth
    — for a module's `migrations/env.py`, which drives its own engine."""
    credential = _credential(client_id, client_secret, tenant_id)
    return {"user": user, "password": _TokenProvider(credential)}, credential


@asynccontextmanager
async def pool(
    database_url: str,
    *,
    user: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
    tenant_id: str | None = None,
    min_size: int = 1,
    max_size: int = 10,
) -> AsyncIterator:
    """A pool. `user` selects identity-based auth: an Entra token is fetched fresh at
    the moment each connection is opened. Omitted — as a test suite's throwaway
    PostgreSQL needs — `database_url` is used exactly as given."""
    if user is None:
        try:
            created = await asyncpg.create_pool(
                asyncpg_dsn(database_url), min_size=min_size, max_size=max_size
            )
        except Exception:
            log.exception("could not connect to %s", _connection_target(database_url))
            raise
        try:
            yield created
        finally:
            await created.close()
        return

    async with _credential(client_id, client_secret, tenant_id) as credential:
        try:
            created = await asyncpg.create_pool(
                asyncpg_dsn(database_url),
                user=user,
                password=_TokenProvider(credential),
                min_size=min_size,
                max_size=max_size,
            )
        except Exception:
            log.exception("could not connect to %s as %s", _connection_target(database_url), user)
            raise
        try:
            yield created
        finally:
            await created.close()


async def fetch_one(conn: Conn, query: str, *args: object) -> asyncpg.Record:
    """`fetchrow` for a statement that cannot answer with nothing.

    An `INSERT ... RETURNING` that comes back empty is not "no rows" — it is a statement
    that did not do what it said. Turning that into `None` hands the caller an optional
    it will dereference two lines later, a long way from the cause.
    """
    row = await conn.fetchrow(query, *args)
    if row is None:
        raise RuntimeError(f"no row from a statement that always returns one: {query.strip()}")
    return row

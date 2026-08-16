"""The connection string, in the two shapes this module needs it.

Duplicated from `agent/db.py` rather than imported — there is no shared library between
modules (docs/architecture.md, "Why no shared library"), and this module owns its own
database (specs/teams-database-connection, "Moduł nie dzieli bazy z innym modułem").
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

# The advisory-lock key this module's migrations take. Advisory locks are scoped to one
# database and this module has its own (`teams-database-connection`, "Moduł nie dzieli
# bazy z innym modułem"), so the value only has to be stable — it carries the module's
# port so a log line naming it says which module took it.
MIGRATION_LOCK_KEY = 8050


class LockNotAcquired(RuntimeError):
    """The lock did not free up within the wait this module allows."""


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
    which this module does not install."""
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
    — for `migrations/env.py`, which drives its own engine."""
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
    the moment each connection is opened. Omitted — as the test suite's throwaway
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
    """`fetchrow` for a statement that cannot answer with nothing — see
    `market_data/db.py`'s twin for the full rationale."""
    row = await conn.fetchrow(query, *args)
    if row is None:
        raise RuntimeError(f"no row from a statement that always returns one: {query.strip()}")
    return row

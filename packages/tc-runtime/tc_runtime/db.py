"""The connection string, the pool and the migration lock. `market_data/db.py` did not come here: at
56.2% it is a different file, not a copy that drifted. The lock key and migrations directory are the caller's."""

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

# What a `store.py` function actually receives: `pool.acquire()` yields a `PoolConnectionProxy`, which
# forwards every method but does not subclass `Connection`.
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
    """Holds a session-level advisory lock on `conn`, or refuses. `pg_try_advisory_lock` in a loop because
    the blocking form has nowhere to put a deadline, and `key` stays the caller's: locks are per database."""
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
    """The URL as SQLAlchemy takes it — asyncpg named, because it is the only driver here. Without the
    suffix alembic defaults to psycopg2, which no module installs."""
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
    """All three present selects a service principal; none present falls through to the managed identity.
    A partial set authenticates as nothing and is rejected."""
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
    """Fetches an Entra token on every call — once per physical connection asyncpg opens, which is what
    renews an expired credential with no separate refresh loop."""

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
async def connect(
    database_url: str,
    *,
    user: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
    tenant_id: str | None = None,
) -> AsyncIterator[asyncpg.Connection]:
    """One connection, closed on the way out. `user` selects identity-based auth: a token is fetched
    fresh and presented as the password, and `database_url` is expected to carry no credential."""
    if user is None:
        try:
            conn = await asyncpg.connect(asyncpg_dsn(database_url))
        except Exception:
            log.exception("could not connect to %s", _connection_target(database_url))
            raise
        try:
            yield conn
        finally:
            await conn.close()
        return

    async with _credential(client_id, client_secret, tenant_id) as credential:
        try:
            conn = await asyncpg.connect(
                asyncpg_dsn(database_url), user=user, password=_TokenProvider(credential)
            )
        except Exception:
            log.exception("could not connect to %s as %s", _connection_target(database_url), user)
            raise
        try:
            yield conn
        finally:
            await conn.close()


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
    """A pool. `user` selects identity-based auth, with a token fetched fresh per connection; omitted,
    `database_url` is used exactly as given."""
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
    """`fetchrow` for a statement that cannot answer with nothing. An `INSERT ... RETURNING` that comes
    back empty did not do what it said, and `None` hands the caller an optional far from the cause."""
    row = await conn.fetchrow(query, *args)
    if row is None:
        raise RuntimeError(f"no row from a statement that always returns one: {query.strip()}")
    return row

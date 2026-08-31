"""The connection string, in the two shapes this module needs it: asyncpg wants a plain
`postgresql://`, SQLAlchemy wants `postgresql+asyncpg://` or it reaches for a driver not installed."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import asyncpg
from azure.identity.aio import ClientSecretCredential, DefaultAzureCredential

# The lock protocol is one copy in the package, being the piece genuinely identical to the others.
# What stays is this module's own wait: thirty minutes, because an index over the candle table outlasts a start.
from tc_runtime.db import LockNotAcquired, advisory_lock

log = logging.getLogger(__name__)

_SCHEME_SEPARATOR = "://"

# Azure Database for PostgreSQL's own resource id — the audience every Entra token presented to it
# must be issued for, managed identity or service principal alike.
_AAD_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"

# The two shapes the database credential takes: a service principal locally, the App Service's
# managed identity in Azure. Named once because three signatures hand the same value along.
Credential = ClientSecretCredential | DefaultAzureCredential

# The advisory-lock key this module's migrations take. Scoped to one database, so the value only has
# to be stable; it carries the module's port so a log line naming it says which module took it.
__all__ = ["MIGRATION_LOCK_KEY", "LockNotAcquired", "advisory_lock"]

MIGRATION_LOCK_KEY = 8020


def asyncpg_dsn(database_url: str) -> str:
    """The URL as asyncpg takes it: scheme without a driver suffix."""
    scheme, separator, rest = database_url.partition(_SCHEME_SEPARATOR)
    if not separator:
        raise ValueError(f"DATABASE_URL is not a usable connection string: {database_url!r}")
    return f"{scheme.split('+', 1)[0]}{_SCHEME_SEPARATOR}{rest}"


def sqlalchemy_url(database_url: str) -> str:
    """The URL as SQLAlchemy takes it — asyncpg named, because it is the only driver here. Without
    the suffix Alembic defaults to psycopg2, and the failure reads like a missing database."""
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
    """Which Entra credential this process authenticates to the database with. All three present
    selects a service principal; none falls through to the managed identity. A partial set is refused."""
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
    """Fetches an Entra token on every call. asyncpg invokes this once per physical connection, which
    is what renews an expiring credential with no refresh loop; the credential caches internally."""

    def __init__(self, credential: Credential) -> None:
        self._credential = credential

    async def __call__(self) -> str:
        try:
            token = await self._credential.get_token(_AAD_SCOPE)
        except Exception as err:
            # Not retried and not papered over with a fallback password — one does not exist.
            # Whatever asyncpg does with this propagates up and fails startup.
            raise RuntimeError(f"could not obtain a database credential: {err}") from err
        return token.token


def identity_connect_args(
    user: str,
    client_id: str | None,
    client_secret: str | None,
    tenant_id: str | None,
) -> tuple[dict[str, object], Credential]:
    """`connect_args` for a SQLAlchemy engine reaching this database with identity auth, for
    `migrations/env.py`. The credential is returned alongside so the caller can close it."""
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
    """A pool, for the parts of the module that run many things at once. A shared connection would
    serialise ingest behind one query, and one per pair would open twenty to write a row a minute."""
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


async def fetch_one(conn: asyncpg.Connection, query: str, *args: object) -> asyncpg.Record:
    """`fetchrow` for a statement that cannot answer with nothing. asyncpg types every `fetchrow` as
    optional, so indexing straight away is right and unprovable at once; a broken invariant reads as one."""
    row = await conn.fetchrow(query, *args)
    if row is None:
        raise RuntimeError(f"no row from a statement that always returns one: {query.strip()}")
    return row

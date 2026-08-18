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

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import asyncpg
from azure.identity.aio import ClientSecretCredential, DefaultAzureCredential

# The lock protocol itself is one copy, in the package: it is the piece of this file that
# was genuinely identical to agent's and teams'. What stays below is what is not — this
# module's own `connect`, its own pool sizing, and the wait it allows, which is thirty
# minutes rather than five because the candle table is the largest thing in the system and
# an index rebuilt over it outlasts several ordinary starts
# (packages-replace-the-hand-copies/design.md, D4).
from tc_runtime.db import LockNotAcquired, advisory_lock

log = logging.getLogger(__name__)

_SCHEME_SEPARATOR = "://"

# Azure Database for PostgreSQL's own resource id — the audience every Entra token
# presented to it must be issued for, whether the caller is a managed identity in Azure
# or a service principal authenticating locally (design.md, "Do bazy — tożsamość").
_AAD_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"

# The two shapes the database credential takes: a service principal locally, the App
# Service's managed identity in Azure. Named once because three signatures hand the same
# value along, and a narrower annotation on any one of them is a claim this module cannot
# keep — which is exactly what it was before, and what a type checker noticed.
Credential = ClientSecretCredential | DefaultAzureCredential

# The advisory-lock key this module's migrations take. Advisory locks are scoped to one
# database and this module has its own, so the value only has to be stable — it carries
# the module's port so a log line naming it says which module took it. `agent/db.py`'s
# twin carries 8030 for the same reason.
# Re-exported so this module's own callers keep one import for its database plumbing.
__all__ = ["MIGRATION_LOCK_KEY", "LockNotAcquired", "advisory_lock"]

MIGRATION_LOCK_KEY = 8020


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


def _connection_target(database_url: str) -> str:
    """`host:port/dbname` — never a credential — for logging a connection failure."""
    parsed = urlparse(asyncpg_dsn(database_url))
    return f"{parsed.hostname}:{parsed.port or 5432}{parsed.path}"


def _credential(
    client_id: str | None, client_secret: str | None, tenant_id: str | None
) -> Credential:
    """Which Entra credential this process authenticates to the database with.

    All three present selects a service principal — local development's own identity
    (`sp-tradingcenter-market-data-dev`, design.md, "Do bazy — tożsamość"), read from
    `.env` since there is no ambient identity on a developer's machine to fall back on.
    None of them present falls through to `DefaultAzureCredential`, which in Azure finds
    the App Service's system-assigned managed identity with no configuration at all. A
    partial set is a misconfiguration, not a mode to guess at — it is rejected rather
    than silently treated as "no credential given".
    """
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
    """Fetches an Entra token on every call.

    asyncpg invokes this once per physical connection it opens — for a `pool`, that
    means every connection the pool opens over its lifetime, not once at startup. That
    is the point: it is what makes a connection opened after the previous token expired
    (specs/market-data-database-connection, "Wygasające poświadczenie jest odnawiane")
    just work, with no separate refresh loop to get wrong. `DefaultAzureCredential`
    caches internally and only reaches the identity endpoint again once the cached token
    is close to expiring, so this is not one network round-trip per connection either.
    """

    def __init__(self, credential: Credential) -> None:
        self._credential = credential

    async def __call__(self) -> str:
        try:
            token = await self._credential.get_token(_AAD_SCOPE)
        except Exception as err:
            # Not retried and not papered over with a fallback password — one does not
            # exist (specs/market-data-database-connection, "Moduł przedstawia się
            # tożsamością, nie hasłem"). Whatever asyncpg does with this propagates up
            # through `pool()`/`connect()` and fails startup.
            raise RuntimeError(f"could not obtain a database credential: {err}") from err
        return token.token


def identity_connect_args(
    user: str,
    client_id: str | None,
    client_secret: str | None,
    tenant_id: str | None,
) -> tuple[dict[str, object], Credential]:
    """`connect_args` for a SQLAlchemy engine reaching this database with identity auth.

    For `migrations/env.py`, which drives its own engine rather than going through
    `pool()`/`connect()` — SQLAlchemy's asyncpg dialect forwards `connect_args` straight
    to `asyncpg.connect()`, so the same `user`/token-callable shape works there
    unchanged. The credential is returned alongside so the caller can close it once the
    engine is done; this function does not own that lifecycle the way `pool()`'s context
    manager does.
    """
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
    """One connection, closed on the way out.

    `user` selects identity-based auth: an Entra token is fetched fresh at the moment
    this connects and presented as the password, and `database_url` itself is expected
    to carry no credential of its own. Omitted — as the test suite's throwaway
    PostgreSQL needs — `database_url` is used exactly as given and the three `client_*`/
    `tenant_id` arguments are ignored. See `_credential()` for what they select when
    `user` is given.
    """
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
    """A pool, for the parts of the module that run as many things at once.

    Ingest needs one: a subscription per tracked pair, each writing as candles close, plus
    whatever backfills are running beside them. A single shared connection would serialise
    all of that behind whichever query got there first, and a connection per pair would
    open twenty of them to write one row a minute each.

    `user`/`client_*`/`tenant_id` — see `connect()`. `app.py`'s lifespan always passes
    `user`; the test suite's own pool usage (if any) does not, for the same reason
    `connect()` does not.
    """
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
    """`fetchrow` for a statement that cannot answer with nothing.

    An `INSERT … RETURNING` and an aggregate `SELECT` each produce exactly one row, but
    asyncpg types every `fetchrow` as optional because most statements can miss. Indexing
    the result straight away is therefore right and unprovable at the same time, and the
    proof lives in the query three lines above — until someone moves one of the two.

    Named here instead of assumed at six call sites. A statement that does come back empty
    is a broken invariant, and reading it as such beats a `TypeError` further down about a
    `None` whose origin is no longer visible.
    """
    row = await conn.fetchrow(query, *args)
    if row is None:
        raise RuntimeError(f"no row from a statement that always returns one: {query.strip()}")
    return row

"""This module's database, and the one number that is its own: how long a start-up waits for the
migration lock. Everything else — the two URL shapes, the Entra credential, the token per connection,
the pool — is the package's, having been identical to it line for line."""

from __future__ import annotations

from tc_runtime.db import (
    Credential,
    LockNotAcquired,
    advisory_lock,
    asyncpg_dsn,
    connect,
    fetch_one,
    identity_connect_args,
    pool,
    sqlalchemy_url,
)

__all__ = [
    "MIGRATION_LOCK_KEY",
    "Credential",
    "LockNotAcquired",
    "advisory_lock",
    "asyncpg_dsn",
    "connect",
    "fetch_one",
    "identity_connect_args",
    "pool",
    "sqlalchemy_url",
]

# The port this module used to have, so two of them cannot wait on each other's key. The wait that
# goes with it is 1500 seconds and lives at the call site: an index over the candle table outlasts a
# start-up, and this is the largest table the repository has.
MIGRATION_LOCK_KEY = 8020

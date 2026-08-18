"""The lock that keeps two processes from migrating one database at once.

Moved here from `modules/agent/tests/test_migrate.py` with the code it tests. What stayed
in the modules is everything that needs *their* migrations: this file drives the lock
against a fake connection, so it asserts the contract and nothing about any one schema.
"""

from __future__ import annotations

import pytest

from tc_runtime.db import LockNotAcquired, advisory_lock

# Any key at all — the point of these tests is the protocol, not the number. The number is
# each module's own, and each module asserts its own (`agent/runtime.py`).
SOME_KEY = 4242


class FakeConnection:
    """Enough of a connection for the two statements `advisory_lock` runs.

    `taken` says the lock is held by somebody else — every `pg_try_advisory_lock` answers
    false, which is the case the wait exists for.
    """

    def __init__(self, *, taken: bool = False) -> None:
        self._taken = taken
        self.unlocked = False

    async def fetchval(self, query: str, key: int) -> bool:
        del key
        if "pg_try_advisory_lock" in query:
            return not self._taken
        self.unlocked = True
        return True


async def test_the_lock_is_released_when_the_body_raises() -> None:
    # The failure that matters: a migration that blew up must not leave the next process
    # waiting on a lock nobody is using.
    conn = FakeConnection()

    with pytest.raises(RuntimeError, match="migration blew up"):
        async with advisory_lock(conn, SOME_KEY, wait=1.0):  # type: ignore[arg-type]
            raise RuntimeError("migration blew up")

    assert conn.unlocked


async def test_a_lock_that_never_frees_up_refuses_rather_than_waits_forever() -> None:
    conn = FakeConnection(taken=True)

    with pytest.raises(LockNotAcquired) as err:
        async with advisory_lock(conn, SOME_KEY, wait=0.05, poll=0.01):  # type: ignore[arg-type]
            pass  # pragma: no cover - the lock is never granted

    assert str(SOME_KEY) in str(err.value)
    # Refusing means never entering the body, so there was nothing to unlock.
    assert not conn.unlocked


async def test_the_key_reaches_postgres_unchanged() -> None:
    """The argument that replaced a per-module constant. A package that quietly used one
    key for every caller would put two modules' migrations behind one lock, in databases
    neither can see — a deadlock with no query to find it by."""
    seen: list[int] = []

    class Recording(FakeConnection):
        async def fetchval(self, query: str, key: int) -> bool:
            seen.append(key)
            return await super().fetchval(query, key)

    conn = Recording()
    async with advisory_lock(conn, 8050, wait=1.0):  # type: ignore[arg-type]
        pass

    assert seen == [8050, 8050], "locked and unlocked with the caller's key, both times"

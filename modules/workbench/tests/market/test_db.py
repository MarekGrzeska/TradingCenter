"""One test, on purpose. The connection string, the credential and the pool are `tc-runtime`'s and
are tested there; what belongs here is that the real pairing works — this module's harness, against
a real PostgreSQL, through the package's `connect`."""

from __future__ import annotations

import pytest

from market_data.db import connect


@pytest.mark.db
async def test_the_test_database_is_reachable(postgres_url: str) -> None:
    """The harness itself, proven once: a container comes up and answers a query. Everything under
    the `db` marker builds on this, so its failure should point here."""
    async with connect(postgres_url) as conn:
        assert await conn.fetchval("SELECT 1") == 1

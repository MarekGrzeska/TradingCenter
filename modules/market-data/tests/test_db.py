from __future__ import annotations

import pytest

from market_data.db import asyncpg_dsn, connect, sqlalchemy_url

PLAIN = "postgresql://market_data:secret@db.internal:5432/market_data"


def test_asyncpg_gets_a_scheme_without_a_driver() -> None:
    assert asyncpg_dsn(PLAIN) == PLAIN
    assert asyncpg_dsn("postgresql+asyncpg://u:p@h:5432/d") == "postgresql://u:p@h:5432/d"


def test_sqlalchemy_gets_the_driver_named() -> None:
    # Without the suffix SQLAlchemy reaches for psycopg2, which this module does not
    # install, and the resulting error reads like an unreachable database.
    assert sqlalchemy_url(PLAIN).startswith("postgresql+asyncpg://")
    assert sqlalchemy_url("postgresql+asyncpg://u:p@h/d") == "postgresql+asyncpg://u:p@h/d"


def test_a_password_with_punctuation_survives_translation() -> None:
    # Only the scheme is rewritten; everything after it is the operator's business.
    url = "postgresql://u:p%40ss+word@h:5432/d?sslmode=require"
    assert asyncpg_dsn(url).endswith("u:p%40ss+word@h:5432/d?sslmode=require")
    assert sqlalchemy_url(url).endswith("u:p%40ss+word@h:5432/d?sslmode=require")


@pytest.mark.parametrize("url", ["", "market_data", "postgresql:/market_data"])
def test_a_connection_string_without_a_scheme_names_itself(url: str) -> None:
    with pytest.raises(ValueError, match="DATABASE_URL"):
        asyncpg_dsn(url)


@pytest.mark.db
async def test_the_test_database_is_reachable(postgres_url: str) -> None:
    """The harness itself, proven once: a container comes up and answers a query.

    Everything under the `db` marker builds on this, so its failure should point here
    rather than at whichever schema test happened to run first.
    """
    async with connect(postgres_url) as conn:
        assert await conn.fetchval("SELECT 1") == 1

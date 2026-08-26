from __future__ import annotations

import logging
from typing import Self

import pytest

from market_data import db
from market_data.db import (
    _connection_target,
    _credential,
    _TokenProvider,
    asyncpg_dsn,
    connect,
    pool,
    sqlalchemy_url,
)

PLAIN = "postgresql://market_data:secret@db.internal:5432/market_data"
NO_CREDENTIAL_URL = "postgresql://db.internal:5432/market_data?sslmode=require"


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
    """The harness itself, proven once: a container comes up and answers a query. Everything under the
    `db` marker builds on this, so its failure should point here."""
    async with connect(postgres_url) as conn:
        assert await conn.fetchval("SELECT 1") == 1



class _FakeToken:
    def __init__(self, value: str) -> None:
        self.token = value


class _FakeCredential:
    """A stand-in for `azure.identity.aio`'s credentials — no MSAL, no network."""

    def __init__(self, tokens: list[str] | None = None, error: Exception | None = None) -> None:
        self._tokens = list(tokens or ["token-1"])
        self._error = error
        self.calls = 0

    async def get_token(self, *scopes: str) -> _FakeToken:
        self.calls += 1
        if self._error is not None:
            raise self._error
        # Repeats the last one once the scripted list is exhausted rather than raising IndexError: a
        # test checking the first two calls should not have to know how many the code makes.
        index = min(self.calls, len(self._tokens)) - 1
        return _FakeToken(self._tokens[index])

    async def close(self) -> None:
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()


def test_connection_target_names_host_port_and_database_never_a_credential() -> None:
    target = _connection_target(PLAIN)
    assert target == "db.internal:5432/market_data"
    assert "market_data" in target  # the role in PLAIN's URL, not the point of this test
    assert "secret" not in target


@pytest.mark.parametrize(
    "client_id,client_secret,tenant_id",
    [
        ("only-client-id", None, None),
        (None, "only-secret", None),
        ("client-id", "secret", None),
        (None, "secret", "tenant-id"),
    ],
)
def test_credential_rejects_a_partial_set(
    client_id: str | None, client_secret: str | None, tenant_id: str | None
) -> None:
    # specs/market-data-database-connection/spec.md, "Moduł przedstawia się tożsamością,
    # nie hasłem" — a half-configured identity is not a fallback to guess at.
    with pytest.raises(ValueError, match="together"):
        _credential(client_id, client_secret, tenant_id)


async def test_token_provider_returns_the_credentials_token() -> None:
    provider = _TokenProvider(_FakeCredential(["the-token"]))
    assert await provider() == "the-token"


async def test_token_provider_wraps_a_credential_failure() -> None:
    # specs/market-data-database-connection, "Poświadczenia nie da się uzyskać": no retry loop, no
    # fallback password — the failure surfaces with the credential named as the cause.
    fake = _FakeCredential(error=RuntimeError("no route to the identity endpoint"))
    provider = _TokenProvider(fake)
    with pytest.raises(RuntimeError, match="credential"):
        await provider()


async def test_connect_with_a_user_passes_it_and_a_token_provider(monkeypatch) -> None:
    captured = {}

    class _FakeConnection:
        async def close(self) -> None:
            pass

    async def fake_connect(dsn, **kwargs):
        captured.update(kwargs)
        return _FakeConnection()

    monkeypatch.setattr(db.asyncpg, "connect", fake_connect)
    monkeypatch.setattr(db, "_credential", lambda *a: _FakeCredential(["t"]))

    async with connect(NO_CREDENTIAL_URL, user="app-tradingcenter-market-data"):
        pass

    assert captured["user"] == "app-tradingcenter-market-data"
    assert isinstance(captured["password"], _TokenProvider)
    assert await captured["password"]() == "t"


async def test_pool_with_a_user_passes_it_and_a_token_provider(monkeypatch) -> None:
    captured = {}

    class _FakePool:
        async def close(self) -> None:
            pass

    async def fake_create_pool(dsn, **kwargs):
        captured.update(kwargs)
        return _FakePool()

    monkeypatch.setattr(db.asyncpg, "create_pool", fake_create_pool)
    monkeypatch.setattr(db, "_credential", lambda *a: _FakeCredential(["t"]))

    async with pool(NO_CREDENTIAL_URL, user="app-tradingcenter-market-data"):
        pass

    assert captured["user"] == "app-tradingcenter-market-data"
    assert isinstance(captured["password"], _TokenProvider)


async def test_a_connection_failure_is_logged_without_the_credential(monkeypatch, caplog) -> None:
    async def fake_connect(dsn, **kwargs):
        raise ConnectionError("connection refused")

    monkeypatch.setattr(db.asyncpg, "connect", fake_connect)
    monkeypatch.setattr(db, "_credential", lambda *a: _FakeCredential(["super-secret-token"]))

    # A `db`-marked test earlier in the session runs Alembic, whose `fileConfig` disables every logger
    # that already existed. Not this test's fixture to own; undone locally instead.
    monkeypatch.setattr(logging.getLogger("market_data.db"), "disabled", False)

    with caplog.at_level(logging.ERROR, logger="market_data.db"), pytest.raises(ConnectionError):
        async with connect(NO_CREDENTIAL_URL, user="app-tradingcenter-market-data"):
            pass

    logged = caplog.text
    assert "db.internal:5432/market_data" in logged
    assert "super-secret-token" not in logged

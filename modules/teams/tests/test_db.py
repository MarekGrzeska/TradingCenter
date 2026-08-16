from __future__ import annotations

import logging
from typing import Self

import pytest
from azure.identity.aio import ClientSecretCredential, DefaultAzureCredential

from teams import db
from teams.db import (
    _connection_target,
    _credential,
    _TokenProvider,
    asyncpg_dsn,
    pool,
    sqlalchemy_url,
)

PLAIN = "postgresql://teams:secret@db.internal:5432/teams"
NO_CREDENTIAL_URL = "postgresql://db.internal:5432/teams?sslmode=require"


def test_asyncpg_gets_a_scheme_without_a_driver() -> None:
    assert asyncpg_dsn(PLAIN) == PLAIN
    assert asyncpg_dsn("postgresql+asyncpg://u:p@h:5432/d") == "postgresql://u:p@h:5432/d"


def test_sqlalchemy_gets_the_driver_named() -> None:
    assert sqlalchemy_url(PLAIN) == "postgresql+asyncpg://teams:secret@db.internal:5432/teams"


@pytest.mark.parametrize("url", ["", "not-a-url-at-all"])
def test_a_connection_string_without_a_scheme_names_itself(url: str) -> None:
    with pytest.raises(ValueError, match="not a usable connection string"):
        asyncpg_dsn(url)


@pytest.mark.db
async def test_the_test_database_is_reachable(postgres_url: str) -> None:
    import asyncpg as _asyncpg

    conn = await _asyncpg.connect(asyncpg_dsn(postgres_url))
    try:
        assert await conn.fetchval("SELECT 1") == 1
    finally:
        await conn.close()


def test_connection_target_names_host_port_and_database_never_a_credential() -> None:
    target = _connection_target(PLAIN)
    assert target == "db.internal:5432/teams"
    assert "secret" not in target


# --- identity: specs/teams-database-connection ---


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
        index = min(self.calls, len(self._tokens)) - 1
        return _FakeToken(self._tokens[index])

    async def close(self) -> None:
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()


def test_credential_selects_a_service_principal_when_all_three_are_given() -> None:
    assert isinstance(_credential("client-id", "client-secret", "tenant-id"), ClientSecretCredential)


def test_credential_falls_back_to_default_when_none_are_given() -> None:
    assert isinstance(_credential(None, None, None), DefaultAzureCredential)


@pytest.mark.parametrize(
    "client_id,client_secret,tenant_id",
    [
        ("only-client-id", None, None),
        (None, "only-secret", None),
        ("client-id", "secret", None),
    ],
)
def test_credential_rejects_a_partial_set(
    client_id: str | None, client_secret: str | None, tenant_id: str | None
) -> None:
    with pytest.raises(ValueError, match="together"):
        _credential(client_id, client_secret, tenant_id)


async def test_token_provider_returns_the_credentials_token() -> None:
    provider = _TokenProvider(_FakeCredential(["the-token"]))
    assert await provider() == "the-token"


async def test_token_provider_fetches_fresh_on_every_call() -> None:
    fake = _FakeCredential(["token-a", "token-b"])
    provider = _TokenProvider(fake)
    assert await provider() == "token-a"
    assert await provider() == "token-b"
    assert fake.calls == 2


async def test_token_provider_wraps_a_credential_failure() -> None:
    fake = _FakeCredential(error=RuntimeError("no route to the identity endpoint"))
    provider = _TokenProvider(fake)
    with pytest.raises(RuntimeError, match="credential"):
        await provider()


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

    async with pool(NO_CREDENTIAL_URL, user="app-tradingcenter-teams"):
        pass

    assert captured["user"] == "app-tradingcenter-teams"
    assert isinstance(captured["password"], _TokenProvider)


async def test_a_connection_failure_is_logged_without_the_credential(monkeypatch, caplog) -> None:
    async def fake_create_pool(dsn, **kwargs):
        raise ConnectionError("connection refused")

    monkeypatch.setattr(db.asyncpg, "create_pool", fake_create_pool)
    monkeypatch.setattr(db, "_credential", lambda *a: _FakeCredential(["super-secret-token"]))

    # See market_data's and agent's twin tests for why this is undone here rather than
    # in migrations/env.py: alembic's fileConfig disables loggers that already exist.
    monkeypatch.setattr(logging.getLogger("teams.db"), "disabled", False)

    with caplog.at_level(logging.ERROR, logger="teams.db"), pytest.raises(ConnectionError):
        async with pool(NO_CREDENTIAL_URL, user="app-tradingcenter-teams"):
            pass

    logged = caplog.text
    assert "db.internal:5432/teams" in logged
    assert "super-secret-token" not in logged

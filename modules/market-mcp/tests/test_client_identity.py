"""Task 5.1: the outbound identity this module presents to market-data."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
import respx

from market_mcp.client import UpstreamClient
from market_mcp.config import Settings
from market_mcp.errors import ToolRefusal

REMOTE_BASE = "https://market-data.example.com"
SCOPE = "api://tradingcenter-market-data/.default"


class _FakeCredential:
    def __init__(self, token: str = "fake-token", fail: bool = False) -> None:
        self.token = token
        self.fail = fail
        self.closed = False
        self.requested_scopes: list[str] = []

    async def get_token(self, *scopes: str):
        self.requested_scopes.extend(scopes)
        if self.fail:
            raise RuntimeError("no identity endpoint reachable")
        return SimpleNamespace(token=self.token)

    async def close(self) -> None:
        self.closed = True


def _remote_settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        market_data_url=REMOTE_BASE, market_data_scope=SCOPE, _env_file=None
    )


@respx.mock
async def test_remote_requests_carry_a_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeCredential(token="abc123")
    monkeypatch.setattr("market_mcp.client.DefaultAzureCredential", lambda: fake)

    route = respx.get(f"{REMOTE_BASE}/pairs").mock(return_value=httpx.Response(200, json=[]))
    client = UpstreamClient(_remote_settings())

    await client.get("/pairs")

    assert route.calls[0].request.headers["Authorization"] == "Bearer abc123"
    assert fake.requested_scopes == [SCOPE]
    await client.aclose()
    assert fake.closed is True


async def test_local_requests_carry_no_authorization_header(settings: Settings) -> None:
    client = UpstreamClient(settings)  # loopback, no scope
    assert client._credential is None
    headers = await client._auth_headers()
    assert headers == {}
    await client.aclose()


@respx.mock
async def test_credential_failure_is_a_tool_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeCredential(fail=True)
    monkeypatch.setattr("market_mcp.client.DefaultAzureCredential", lambda: fake)

    client = UpstreamClient(_remote_settings())

    with pytest.raises(ToolRefusal, match="could not obtain a credential"):
        await client.get("/pairs")
    await client.aclose()

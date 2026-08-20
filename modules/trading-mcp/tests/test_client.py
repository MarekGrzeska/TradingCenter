"""client.py: authentication, retry-vs-no-retry, and error mapping."""

from __future__ import annotations

import httpx
import pytest
import respx
from azure.core.exceptions import AzureError, ClientAuthenticationError
from azure.identity.aio import DefaultAzureCredential

from trading_mcp.client import GATEWAY_KEY_HEADER, GatewayClient
from trading_mcp.config import Settings
from trading_mcp.errors import GatewayRefused, GatewayUnavailable

BASE = "http://127.0.0.1:8010"


@pytest.fixture
def client(settings: Settings) -> GatewayClient:
    return GatewayClient(settings)


@respx.mock
async def test_every_request_carries_the_gateway_key(client: GatewayClient) -> None:
    route = respx.get(f"{BASE}/positions").mock(return_value=httpx.Response(200, json=[]))

    await client.get("/positions")

    assert route.calls.last.request.headers[GATEWAY_KEY_HEADER] == "test-gateway-key"
    await client.aclose()


@respx.mock
async def test_a_single_5xx_read_is_retried_and_can_succeed(client: GatewayClient) -> None:
    route = respx.get(f"{BASE}/positions").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json=[])]
    )

    result = await client.get("/positions")

    assert result == []
    assert route.call_count == 2
    await client.aclose()


@respx.mock
async def test_a_persistent_5xx_read_is_refused_after_one_retry(client: GatewayClient) -> None:
    route = respx.get(f"{BASE}/positions").mock(
        return_value=httpx.Response(503, json={"detail": "unavailable"})
    )

    with pytest.raises(GatewayRefused) as excinfo:
        await client.get("/positions")

    assert excinfo.value.status_code == 503
    assert route.call_count == 2
    await client.aclose()


@respx.mock
async def test_a_write_is_never_retried_on_5xx(client: GatewayClient) -> None:
    route = respx.post(f"{BASE}/orders").mock(
        return_value=httpx.Response(503, json={"detail": "unavailable"})
    )

    with pytest.raises(GatewayRefused):
        await client.write("POST", "/orders", json={"symbol": "GOLD"})

    assert route.call_count == 1
    await client.aclose()


@respx.mock
async def test_a_write_is_never_retried_after_a_timeout(client: GatewayClient) -> None:
    route = respx.post(f"{BASE}/orders").mock(side_effect=httpx.ReadTimeout("timed out"))

    with pytest.raises(GatewayUnavailable):
        await client.write("POST", "/orders", json={"symbol": "GOLD"})

    assert route.call_count == 1
    await client.aclose()


@respx.mock
async def test_a_4xx_is_a_refusal_naming_the_detail(client: GatewayClient) -> None:
    respx.post(f"{BASE}/orders").mock(
        return_value=httpx.Response(422, json={"detail": "level is required for LIMIT/STOP"})
    )

    with pytest.raises(GatewayRefused, match="level is required"):
        await client.write("POST", "/orders", json={"symbol": "GOLD"})
    await client.aclose()


@respx.mock
async def test_a_validation_list_is_flattened_rather_than_dropped(
    client: GatewayClient,
) -> None:
    """The gateway's other refusal shape. Handed over raw it reaches the model as the
    repr of a list of dicts; flattened, it names the field the order got wrong — which is
    the only form a caller can act on."""
    respx.post(f"{BASE}/orders").mock(
        return_value=httpx.Response(
            422,
            json={
                "detail": [
                    {
                        "type": "missing",
                        "loc": ["body", "size"],
                        "msg": "Field required",
                        "url": "https://errors.pydantic.dev/2.11/v/missing",
                    }
                ]
            },
        )
    )

    with pytest.raises(GatewayRefused) as err:
        await client.write("POST", "/orders", json={"symbol": "GOLD"})

    assert "size: Field required" in str(err.value)
    assert "pydantic.dev" not in str(err.value)
    await client.aclose()


@respx.mock
async def test_a_json_body_that_is_not_an_object_is_still_a_refusal(
    client: GatewayClient,
) -> None:
    respx.get(f"{BASE}/positions").mock(return_value=httpx.Response(500, json=["boom"]))

    with pytest.raises(GatewayRefused) as err:
        await client.get("/positions")

    assert "AttributeError" not in str(err.value)
    await client.aclose()


@respx.mock
async def test_timeout_is_a_gateway_unavailable(client: GatewayClient) -> None:
    respx.get(f"{BASE}/positions").mock(side_effect=httpx.ReadTimeout("timed out"))

    with pytest.raises(GatewayUnavailable, match="did not respond"):
        await client.get("/positions")
    await client.aclose()


@respx.mock
async def test_unreachable_gateway_is_a_gateway_unavailable(client: GatewayClient) -> None:
    respx.get(f"{BASE}/positions").mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(GatewayUnavailable, match="unreachable"):
        await client.get("/positions")
    await client.aclose()


# --- the-gateway-door-authenticates: the credential's shape follows the place ---------


class _FakeToken:
    def __init__(self, token: str) -> None:
        self.token = token


class _FakeCredential:
    def __init__(self, token: str | None = "a-token") -> None:
        self._token = token
        self.scopes: list[str] = []

    async def get_token(self, scope: str) -> _FakeToken:
        self.scopes.append(scope)
        if self._token is None:
            raise ClientAuthenticationError("no identity on this machine")
        return _FakeToken(self._token)

    async def close(self) -> None:
        pass


@respx.mock
async def test_with_a_scope_every_request_carries_a_token_beside_the_key(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    credential = _FakeCredential()
    monkeypatch.setattr("trading_mcp.client.DefaultAzureCredential", lambda: credential)
    scoped = settings.model_copy(update={"capital_gateway_scope": "api://gateway/.default"})
    client = GatewayClient(scoped)
    route = respx.get(f"{BASE}/positions").mock(return_value=httpx.Response(200, json=[]))

    await client.get("/positions")

    request = route.calls.last.request
    assert request.headers[GATEWAY_KEY_HEADER] == "test-gateway-key"
    assert request.headers["Authorization"] == "Bearer a-token"
    assert credential.scopes == ["api://gateway/.default"]
    await client.aclose()


@respx.mock
async def test_without_a_scope_no_token_is_asked_for(client: GatewayClient) -> None:
    # The local shape: nothing to ask, and the key is the whole credential.
    route = respx.get(f"{BASE}/positions").mock(return_value=httpx.Response(200, json=[]))

    await client.get("/positions")

    assert "Authorization" not in route.calls.last.request.headers
    await client.aclose()


@respx.mock
async def test_a_token_that_cannot_be_had_leaves_the_key_to_do_the_work(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Not a refusal to start: until the gateway's door requires a token, the key is what
    # gets in, and refusing here would be this module taking itself down over a credential
    # nothing yet asks for.
    monkeypatch.setattr("trading_mcp.client.DefaultAzureCredential", lambda: _FakeCredential(None))
    scoped = settings.model_copy(update={"capital_gateway_scope": "api://gateway/.default"})
    client = GatewayClient(scoped)
    route = respx.get(f"{BASE}/capabilities").mock(
        return_value=httpx.Response(200, json={"environment": "demo"})
    )

    await client.ensure_demo_environment()

    assert "Authorization" not in route.calls.last.request.headers
    await client.aclose()


@respx.mock
async def test_a_gateway_that_refuses_the_demo_check_stops_the_port_opening(
    settings: Settings,
) -> None:
    # Where "cannot present itself" is actually answered: by the gateway, on the check
    # that runs before uvicorn listens. After the door is flipped, a module without a
    # usable token lands here.
    client = GatewayClient(settings)
    respx.get(f"{BASE}/capabilities").mock(return_value=httpx.Response(401))

    with pytest.raises(GatewayRefused):
        await client.ensure_demo_environment()

    await client.aclose()


async def test_the_async_transport_is_installed() -> None:
    """The real credential, not a double — which is the whole point of this test.

    Every other test here monkeypatches `DefaultAzureCredential`, so none of them touches
    the transport `azure.identity.aio` imports lazily on the first `get_token`. Shipping
    without `aiohttp` is therefore an `ImportError` in production and a green suite here:
    that is exactly what happened on 20 August 2026, when this container exited 1 five
    seconds into start-up, because the demo check is the first thing that asks for a token.

    Any `AzureError` is a pass — on a machine with no identity the answer is a refusal, and
    a refusal proves the pipeline was built. `ImportError` is the failure being guarded.
    """
    credential = DefaultAzureCredential()
    try:
        await credential.get_token("api://tradingcenter-capital-gateway/.default")
    except AzureError:
        pass
    finally:
        await credential.close()

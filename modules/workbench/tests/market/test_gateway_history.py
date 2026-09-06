from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx
from azure.core.exceptions import ClientAuthenticationError

from market_data.errors import GatewayRefused, GatewayUnreachable, UnreadablePayload
from market_data.gateway import GATEWAY_KEY_HEADER, GatewayHistory, http_client
from market_data.models import CandleSource, PriceSide, Resolution

BASE_URL = "http://gateway.test:8010"
HISTORY_URL = f"{BASE_URL}/instruments/US100/history"


def gateway_candle(ts: str, close: float = 100.5) -> dict:
    return {
        "ts": ts,
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": close,
        "volume": 1000.0,
        "resolution": "MINUTE",
    }


def gateway_history(candles: list[dict], **overrides) -> dict:
    return {
        "candles": candles,
        "count": len(candles),
        "requested": 1000,
        "requests": 1,
        "resolution": "MINUTE",
        "first_ts": candles[0]["ts"] if candles else None,
        "last_ts": candles[-1]["ts"] if candles else None,
        "history_ended": False,
        **overrides,
    }


@pytest.fixture
async def reader():
    async with httpx.AsyncClient() as client:
        yield GatewayHistory(BASE_URL, client)


@respx.mock
async def test_a_history_read_comes_back_as_closed_bid_candles(reader: GatewayHistory) -> None:
    respx.get(HISTORY_URL).mock(
        return_value=httpx.Response(200, json=gateway_history([gateway_candle("2026-08-07T12:00:00Z")]))
    )

    page = await reader.history("US100", Resolution.MINUTE, 1000)

    [candle] = page.candles
    assert candle.symbol == "US100"
    assert candle.resolution is Resolution.MINUTE
    assert candle.period_start == datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
    assert candle.close == 100.5
    # Everything from a history read is settled and on the bid side. `source` is what
    # later lets a history value outrank a streamed one for the same period.
    assert candle.forming is False
    assert candle.price_side is PriceSide.BID
    assert candle.source is CandleSource.HISTORY


@respx.mock
async def test_the_request_asks_for_what_it_was_told_to(reader: GatewayHistory) -> None:
    route = respx.get(HISTORY_URL).mock(
        return_value=httpx.Response(200, json=gateway_history([]))
    )

    await reader.history("US100", Resolution.HOUR_4, 5000)

    assert route.calls.last.request.url.params["resolution"] == "HOUR_4"
    assert route.calls.last.request.url.params["bars"] == "5000"


@respx.mock
async def test_a_deep_read_is_one_request_not_a_page_walk(reader: GatewayHistory) -> None:
    # The gateway pages past the provider's ceiling itself, anchoring on data rather than the clock.
    # A second implementation here would drift from it — and the gateway owns the rate gate.
    route = respx.get(HISTORY_URL).mock(
        return_value=httpx.Response(200, json=gateway_history([], requested=50_000, requests=63))
    )

    page = await reader.history("US100", Resolution.MINUTE, 50_000)

    assert route.call_count == 1
    assert page.requested == 50_000
    # Passed through so an operator can see why a fill was slow rather than guess.
    assert page.requests == 63


@respx.mock
async def test_the_end_of_provider_history_is_carried_through(reader: GatewayHistory) -> None:
    # This becomes the left edge of a coverage range. Dropping it leaves the module
    # asking forever for data that does not exist.
    respx.get(HISTORY_URL).mock(
        return_value=httpx.Response(200, json=gateway_history([], history_ended=True))
    )

    assert (await reader.history("US100", Resolution.MINUTE, 1000)).history_ended is True


@respx.mock
async def test_candles_come_back_oldest_first(reader: GatewayHistory) -> None:
    respx.get(HISTORY_URL).mock(
        return_value=httpx.Response(
            200,
            json=gateway_history(
                [
                    gateway_candle("2026-08-07T12:02:00Z"),
                    gateway_candle("2026-08-07T12:00:00Z"),
                    gateway_candle("2026-08-07T12:01:00Z"),
                ]
            ),
        )
    )

    page = await reader.history("US100", Resolution.MINUTE, 1000)

    assert [c.period_start.minute for c in page.candles] == [0, 1, 2]


@respx.mock
async def test_a_page_mixing_zoned_and_unzoned_timestamps_is_still_in_time_order(
    reader: GatewayHistory,
) -> None:
    # The gateway sorts on the string, which is chronological only while every timestamp carries the
    # same zone marker, and some carry none. Sorting on the instant keeps the two consistent.
    respx.get(HISTORY_URL).mock(
        return_value=httpx.Response(
            200,
            json=gateway_history(
                [
                    gateway_candle("2026-08-07T12:02:00"),
                    gateway_candle("2026-08-07T12:01:00Z"),
                ]
            ),
        )
    )

    page = await reader.history("US100", Resolution.MINUTE, 1000)

    assert [c.period_start.minute for c in page.candles] == [1, 2]


@respx.mock
async def test_an_empty_history_is_not_an_error(reader: GatewayHistory) -> None:
    respx.get(HISTORY_URL).mock(
        return_value=httpx.Response(200, json=gateway_history([]))
    )
    assert (await reader.history("US100", Resolution.MINUTE, 1000)).candles == []


@respx.mock
async def test_a_missing_edge_survives_the_crossing(reader: GatewayHistory) -> None:
    candle = gateway_candle("2026-08-07T12:00:00Z")
    candle["close"] = None
    respx.get(HISTORY_URL).mock(
        return_value=httpx.Response(200, json=gateway_history([candle]))
    )

    assert (await reader.history("US100", Resolution.MINUTE, 1000)).candles[0].close is None


@respx.mock
async def test_a_before_moment_is_sent_as_an_anchor(reader: GatewayHistory) -> None:
    route = respx.get(HISTORY_URL).mock(
        return_value=httpx.Response(200, json=gateway_history([]))
    )
    anchor = datetime(2024, 1, 15, tzinfo=UTC)

    await reader.history("US100", Resolution.MINUTE, 1000, before=anchor)

    sent = route.calls.last.request.url.params
    assert sent["before"] == anchor.isoformat()


@respx.mock
async def test_no_before_moment_omits_the_anchor(reader: GatewayHistory) -> None:
    route = respx.get(HISTORY_URL).mock(
        return_value=httpx.Response(200, json=gateway_history([]))
    )

    await reader.history("US100", Resolution.MINUTE, 1000)

    assert "before" not in route.calls.last.request.url.params



@respx.mock
async def test_a_refusal_carries_the_reason_the_gateway_gave(reader: GatewayHistory) -> None:
    respx.get(HISTORY_URL).mock(
        return_value=httpx.Response(404, json={"detail": "unknown symbol 'US100'"})
    )

    with pytest.raises(GatewayRefused) as err:
        await reader.history("US100", Resolution.MINUTE, 1000)

    assert err.value.status_code == 404
    assert "unknown symbol" in err.value.detail


@respx.mock
async def test_a_refusal_without_a_detail_still_says_something(reader: GatewayHistory) -> None:
    respx.get(HISTORY_URL).mock(return_value=httpx.Response(502, text="upstream is down"))

    with pytest.raises(GatewayRefused, match="upstream is down"):
        await reader.history("US100", Resolution.MINUTE, 1000)


@respx.mock
async def test_a_gateway_that_does_not_answer_is_named_as_such(reader: GatewayHistory) -> None:
    # Distinct from a refusal because only one of the two is worth retrying the same way.
    respx.get(HISTORY_URL).mock(side_effect=httpx.ConnectError("connection refused"))

    with pytest.raises(GatewayUnreachable, match="US100"):
        await reader.history("US100", Resolution.MINUTE, 1000)


@respx.mock
async def test_an_answer_that_is_not_history_is_named_as_drift(reader: GatewayHistory) -> None:
    # A refusal is the gateway working and saying no; this is the contract between the
    # two modules having moved. Retrying it forever would hide that.
    respx.get(HISTORY_URL).mock(return_value=httpx.Response(200, json={"totally": "different"}))

    with pytest.raises(UnreadablePayload):
        await reader.history("US100", Resolution.MINUTE, 1000)


@respx.mock
async def test_a_candle_with_no_timestamp_is_not_silently_stored(reader: GatewayHistory) -> None:
    respx.get(HISTORY_URL).mock(
        return_value=httpx.Response(200, json=gateway_history([gateway_candle("")]))
    )

    with pytest.raises(ValueError, match="no timestamp"):
        await reader.history("US100", Resolution.MINUTE, 1000)



@respx.mock
async def test_the_shared_client_carries_the_caller_key_on_every_request() -> None:
    route = respx.get(HISTORY_URL).mock(
        return_value=httpx.Response(200, json=gateway_history([gateway_candle("2026-08-07T12:00:00Z")]))
    )

    async with http_client("the-caller-key") as client:
        await GatewayHistory(BASE_URL, client).history("US100", Resolution.MINUTE, 1000)

    assert route.calls.last.request.headers[GATEWAY_KEY_HEADER] == "the-caller-key"


@respx.mock
async def test_a_401_from_the_gateway_is_a_refusal_not_an_empty_history(
    reader: GatewayHistory,
) -> None:
    # capital-gateway answers a missing or wrong caller key with 401 before it asks the provider.
    # That must surface as GatewayRefused, never as an empty, successfully-read page.
    respx.get(HISTORY_URL).mock(
        return_value=httpx.Response(401, json={"detail": "missing or invalid caller key"})
    )

    with pytest.raises(GatewayRefused) as err:
        await reader.history("US100", Resolution.MINUTE, 1000)

    assert err.value.status_code == 401



class _FakeToken:
    def __init__(self, token: str) -> None:
        self.token = token


class _FakeCredential:
    """What `DefaultAzureCredential` is here: something that answers with a token, or
    refuses to. The real one reaches the instance metadata endpoint, which no test has."""

    def __init__(self, token: str | None = "a-token") -> None:
        self._token = token
        self.scopes: list[str] = []

    async def get_token(self, scope: str) -> _FakeToken:
        self.scopes.append(scope)
        if self._token is None:
            raise ClientAuthenticationError("no identity on this machine")
        return _FakeToken(self._token)

    async def close(self) -> None:  # pragma: no cover - httpx never calls this
        pass


@respx.mock
async def test_a_module_with_an_identity_carries_a_token_beside_the_key(monkeypatch) -> None:
    credential = _FakeCredential()
    monkeypatch.setattr("market_data.gateway._http.DefaultAzureCredential", lambda: credential)
    route = respx.get(HISTORY_URL).mock(
        return_value=httpx.Response(200, json=gateway_history([gateway_candle("2026-08-07T12:00:00Z")]))
    )

    async with http_client("the-caller-key", "api://gateway/.default") as client:
        await GatewayHistory(BASE_URL, client).history("US100", Resolution.MINUTE, 1000)

    request = route.calls.last.request
    assert request.headers[GATEWAY_KEY_HEADER] == "the-caller-key"
    assert request.headers["Authorization"] == "Bearer a-token"
    assert credential.scopes == ["api://gateway/.default"]


@respx.mock
async def test_without_a_scope_the_key_is_the_whole_credential() -> None:
    # Local work: no directory, nothing to ask for a token, and that is a supported
    # configuration rather than a degraded one.
    route = respx.get(HISTORY_URL).mock(
        return_value=httpx.Response(200, json=gateway_history([gateway_candle("2026-08-07T12:00:00Z")]))
    )

    async with http_client("the-caller-key") as client:
        await GatewayHistory(BASE_URL, client).history("US100", Resolution.MINUTE, 1000)

    request = route.calls.last.request
    assert request.headers[GATEWAY_KEY_HEADER] == "the-caller-key"
    assert "Authorization" not in request.headers


@respx.mock
async def test_a_token_that_cannot_be_had_leaves_the_key_to_do_the_work(monkeypatch) -> None:
    # Between the deploy and the flip, the key is still what opens the gateway's door. Refusing here
    # would stop the archive filling over a credential nothing yet asks for.
    monkeypatch.setattr(
        "market_data.gateway._http.DefaultAzureCredential", lambda: _FakeCredential(None)
    )
    route = respx.get(HISTORY_URL).mock(
        return_value=httpx.Response(200, json=gateway_history([gateway_candle("2026-08-07T12:00:00Z")]))
    )

    async with http_client("the-caller-key", "api://gateway/.default") as client:
        await GatewayHistory(BASE_URL, client).history("US100", Resolution.MINUTE, 1000)

    request = route.calls.last.request
    assert request.headers[GATEWAY_KEY_HEADER] == "the-caller-key"
    assert "Authorization" not in request.headers


@respx.mock
async def test_a_401_after_the_door_is_flipped_is_still_a_refusal(monkeypatch) -> None:
    monkeypatch.setattr(
        "market_data.gateway._http.DefaultAzureCredential", lambda: _FakeCredential(None)
    )
    respx.get(HISTORY_URL).mock(return_value=httpx.Response(401, json={"detail": "unauthorized"}))

    async with http_client("the-caller-key", "api://gateway/.default") as client:
        with pytest.raises(GatewayRefused):
            await GatewayHistory(BASE_URL, client).history("US100", Resolution.MINUTE, 1000)

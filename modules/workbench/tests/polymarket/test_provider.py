"""The door to Polymarket: what it retries, what it refuses, and what it always sends."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
import respx

from polymarket_data import provider

GAMMA = "https://gamma.test"
CLOB = "https://clob.test"


def make_client(http: httpx.AsyncClient, **kwargs) -> provider.PolymarketClient:
    return provider.PolymarketClient(
        http, gamma_base_url=GAMMA, clob_base_url=CLOB, concurrency=4, **kwargs
    )


@pytest.fixture
async def http():
    async with httpx.AsyncClient(
        headers={"User-Agent": "tradingcenter-test/1.0", "Accept": "application/json"}
    ) as client:
        yield client


class TestRefusalsAreToldApart:
    @respx.mock
    async def test_a_404_is_an_answer_not_a_failure(self, http) -> None:
        """"The provider has no such event" tells the operator something; "the provider
        refused" tells this module to try again. They must not read alike."""
        route = respx.get(f"{GAMMA}/events/slug/nope").mock(
            return_value=httpx.Response(404, json={"error": "slug not found"})
        )

        with pytest.raises(provider.ProviderHasNothing):
            await make_client(http).event_by_reference("nope")

        assert route.call_count == 1, "a 404 must not be retried; it will not change"

    @respx.mock
    async def test_a_bad_request_is_refused_once_and_carries_the_providers_own_words(
        self, http
    ) -> None:
        """The usual case is the fifteen-day window exceeded, and the provider names it
        better than any wrapper would."""
        route = respx.get(f"{CLOB}/prices-history").mock(
            return_value=httpx.Response(
                400, json={"error": "invalid filters: 'startTs' and 'endTs' interval is too long"}
            )
        )

        with pytest.raises(provider.ProviderRefused, match="interval is too long"):
            await make_client(http).price_history(
                "token", since=_moment(0), until=_moment(60 * 86400)
            )

        assert route.call_count == 1

    @respx.mock
    async def test_a_rate_limit_is_backed_off_and_then_succeeds(self, http) -> None:
        respx.get(f"{GAMMA}/events/slug/x").mock(
            side_effect=[
                httpx.Response(429, text="slow down"),
                httpx.Response(200, json=_event()),
            ]
        )

        event = await make_client(http).event_by_reference("x")

        assert event.slug == "an-event"

    @respx.mock
    async def test_a_provider_that_keeps_failing_gives_up_and_says_so(self, http) -> None:
        respx.get(f"{GAMMA}/events/slug/x").mock(return_value=httpx.Response(503))

        with pytest.raises(provider.ProviderRefused, match="503"):
            await make_client(http, max_attempts=2).event_by_reference("x")

    @respx.mock
    async def test_a_body_that_is_not_json_is_a_changed_shape_not_a_refusal(self, http) -> None:
        respx.get(f"{GAMMA}/events/slug/x").mock(
            return_value=httpx.Response(200, text="<html>maintenance</html>")
        )

        with pytest.raises(provider.ProviderUnusable):
            await make_client(http).event_by_reference("x")


class TestTheHeaderTheProvidersEdgeReads:
    @respx.mock
    async def test_every_request_names_this_module(self, http) -> None:
        """The provider's edge selects on User-Agent — measured 22 August 2026. A library's default is a
        value somebody else decides; this module sends its own so a dependency bump cannot change it."""
        route = respx.get(f"{GAMMA}/events/slug/x").mock(
            return_value=httpx.Response(200, json=_event())
        )

        await make_client(http).event_by_reference("x")

        assert route.calls.last.request.headers["user-agent"].startswith("tradingcenter")

    async def test_the_client_helper_sets_it_once_rather_than_per_call(self) -> None:
        async with provider.client(
            gamma_base_url=GAMMA,
            clob_base_url=CLOB,
            user_agent="tradingcenter-polymarket-data/0.1",
            concurrency=2,
        ) as built:
            assert isinstance(built, provider.PolymarketClient)


class TestReads:
    @respx.mock
    async def test_the_history_window_is_sent_as_seconds(self, http) -> None:
        route = respx.get(f"{CLOB}/prices-history").mock(
            return_value=httpx.Response(200, json={"history": [{"t": 100, "p": "0.5"}]})
        )

        points = await make_client(http).price_history(
            "tok", since=_moment(0), until=_moment(3600)
        )

        assert points == [(100, Decimal("0.5"))]
        request = route.calls.last.request
        assert request.url.params["startTs"] == "0"
        assert request.url.params["endTs"] == "3600"
        assert request.url.params["market"] == "tok"

    @respx.mock
    async def test_browsing_asks_the_provider_for_its_own_ordering(self, http) -> None:
        route = respx.get(f"{GAMMA}/events").mock(return_value=httpx.Response(200, json=[]))

        await make_client(http).browse_events(tag_id="2", limit=5, offset=10)

        params = route.calls.last.request.url.params
        assert params["tag_id"] == "2"
        assert params["limit"] == "5"
        assert params["offset"] == "10"
        assert params["closed"] == "false"

    @respx.mock
    async def test_search_reads_the_events_out_of_the_search_answer(self, http) -> None:
        respx.get(f"{GAMMA}/public-search").mock(
            return_value=httpx.Response(200, json={"events": [{"slug": "a"}], "pagination": {}})
        )

        found = await make_client(http).search_events("tariffs")

        assert [event["slug"] for event in found] == ["a"]


def _moment(seconds: int) -> datetime:
    return datetime.fromtimestamp(seconds, UTC)


def _event() -> dict:
    return {
        "id": "1",
        "slug": "an-event",
        "title": "An event",
        "markets": [
            {
                "id": "m",
                "question": "Will it?",
                "outcomes": json.dumps(["Yes", "No"]),
                "clobTokenIds": json.dumps(["t0", "t1"]),
                "outcomePrices": json.dumps(["0.5", "0.5"]),
                "closed": False,
            }
        ],
    }

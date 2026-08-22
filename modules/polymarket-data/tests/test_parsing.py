"""The provider's payloads, read without touching the network.

Every awkward thing about Polymarket's shapes is in here rather than in the client, which is
why these are unit tests: `outcomes`, `outcomePrices` and `clobTokenIds` arrive as JSON
inside a string, aligned by position, and nothing in the payload says so.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from polymarket_data import parsing
from polymarket_data.parsing import ProviderPayloadUnusable


def market_payload(
    *,
    market_id: str = "m-1",
    outcomes: tuple[str, ...] = ("Yes", "No"),
    prices: tuple[str, ...] | None = ("0.465", "0.535"),
    tokens: tuple[str, ...] | None = None,
    closed: bool = False,
    last_trade: str | None = "0.46",
    **extra,
) -> dict:
    payload = {
        "id": market_id,
        "question": "Will it?",
        "outcomes": json.dumps(list(outcomes)),
        "clobTokenIds": json.dumps(
            list(tokens if tokens is not None else [f"{market_id}-t{i}" for i in range(len(outcomes))])
        ),
        "closed": closed,
    }
    if prices is not None:
        payload["outcomePrices"] = json.dumps(list(prices))
    if last_trade is not None:
        payload["lastTradePrice"] = last_trade
    return payload | extra


def event_payload(*markets: dict, **extra) -> dict:
    return {
        "id": "30829",
        "slug": "an-event",
        "title": "An event",
        "markets": list(markets) or [market_payload()],
    } | extra


class TestSlugFromWhateverTheCallerHad:
    @pytest.mark.parametrize(
        "reference",
        [
            "world-cup-winner",
            "https://polymarket.com/event/world-cup-winner",
            "https://polymarket.com/event/world-cup-winner/some-market?tid=1",
            "  https://polymarket.com/market/world-cup-winner  ",
        ],
    )
    def test_an_address_and_a_slug_reach_the_same_observation(self, reference: str) -> None:
        """The operator copies an address; the model has a slug from a search. Two code
        paths could disagree about which event that is, so there is one."""
        assert parsing.slug_from(reference) == "world-cup-winner"

    def test_something_that_is_neither_is_refused(self) -> None:
        with pytest.raises(ProviderPayloadUnusable, match="neither"):
            parsing.slug_from("https://example.test/not/polymarket")


class TestMarkets:
    def test_json_inside_a_string_is_read(self) -> None:
        market = parsing.market_from(market_payload())
        assert [outcome.name for outcome in market.outcomes] == ["Yes", "No"]
        assert market.outcomes[0].token_id == "m-1-t0"

    def test_a_plain_list_is_read_too(self) -> None:
        """The change that would otherwise break every event on the day it lands, silently,
        by parsing nothing."""
        payload = market_payload()
        payload["outcomes"] = ["Yes", "No"]
        payload["clobTokenIds"] = ["a", "b"]
        assert [o.token_id for o in parsing.market_from(payload).outcomes] == ["a", "b"]

    def test_more_than_two_outcomes_are_kept(self) -> None:
        market = parsing.market_from(
            market_payload(outcomes=("A", "B", "C", "D"), prices=("0.1", "0.2", "0.3", "0.4"))
        )
        assert len(market.outcomes) == 4
        assert [o.position for o in market.outcomes] == [0, 1, 2, 3]

    def test_outcomes_and_tokens_of_different_lengths_are_refused(self) -> None:
        """Position is the only thing pairing an outcome with the token its price is asked
        for by. Guessing writes one outcome's price under another outcome's name."""
        with pytest.raises(ProviderPayloadUnusable, match="paired by position"):
            parsing.market_from(market_payload(outcomes=("Yes", "No"), tokens=("only-one",)))

    def test_a_market_with_no_tokens_is_refused(self) -> None:
        with pytest.raises(ProviderPayloadUnusable, match="no outcomes or no tokens"):
            parsing.market_from(market_payload(tokens=()))


class TestResolution:
    def test_a_closed_market_priced_one_and_zero_names_its_winner(self) -> None:
        market = parsing.market_from(market_payload(closed=True, prices=("1", "0")))
        assert market.resolved_outcome == "Yes"
        assert market.resolved

    def test_an_open_market_at_a_high_price_is_not_resolved(self) -> None:
        """A market trading at 0,999 an hour before it resolves has not resolved."""
        market = parsing.market_from(market_payload(prices=("0.999", "0.001")))
        assert market.resolved_outcome is None

    def test_a_closed_market_with_an_ambiguous_shape_is_left_unresolved(self) -> None:
        # Two outcomes at 1 is not an answer; recording one of them would be inventing it.
        market = parsing.market_from(
            market_payload(closed=True, outcomes=("A", "B", "C"), prices=("1", "1", "0"))
        )
        assert market.resolved_outcome is None


class TestEvents:
    def test_one_unreadable_market_does_not_cost_the_other_hundred(self) -> None:
        good = market_payload(market_id="ok")
        broken = market_payload(market_id="bad", tokens=("one",))
        event = parsing.event_from(event_payload(good, broken))
        assert [market.provider_market_id for market in event.markets] == ["ok"]

    def test_an_event_with_nothing_readable_is_refused(self) -> None:
        with pytest.raises(ProviderPayloadUnusable, match="no market this module can read"):
            parsing.event_from(event_payload(market_payload(tokens=())))

    def test_an_answer_that_is_not_an_event_is_refused(self) -> None:
        """Distinct from "the provider has no such event" and from "the provider refused" —
        this is a shape that changed, and it must not read as either."""
        with pytest.raises(ProviderPayloadUnusable, match="not an event"):
            parsing.event_from({"detail": "nope"})


class TestPrices:
    def test_every_outcome_of_every_market_is_priced_from_one_payload(self) -> None:
        """The measurement the sampler rests on: `outcomePrices` is the order book's
        midpoint for every outcome at once, so one request prices the whole event."""
        payload = event_payload(
            market_payload(market_id="a", prices=("0.465", "0.535")),
            market_payload(
                market_id="b", outcomes=("X", "Y", "Z"), prices=("0.2", "0.3", "0.5"),
                last_trade=None,
            ),
        )

        prices = parsing.prices_from(payload)

        assert prices["a-t0"] == (Decimal("0.465"), Decimal("0.46"))
        assert prices["a-t1"] == (Decimal("0.535"), None)
        assert prices["b-t2"] == (Decimal("0.5"), None)

    def test_the_last_trade_is_not_invented_for_the_other_side(self) -> None:
        """`lastTradePrice` sits on the market and describes its first outcome. A complement
        computed for the second would be a number that looks like data."""
        prices = parsing.prices_from(event_payload(market_payload(market_id="a")))
        assert prices["a-t1"][1] is None

    def test_a_price_outside_the_interval_is_not_a_price(self) -> None:
        prices = parsing.prices_from(
            event_payload(market_payload(market_id="a", prices=("7", "0.5"), last_trade=None))
        )
        assert "a-t0" not in prices
        assert prices["a-t1"][0] == Decimal("0.5")


class TestHistory:
    def test_points_come_back_oldest_first(self) -> None:
        payload = {"history": [{"t": 30, "p": "0.3"}, {"t": 10, "p": "0.1"}, {"t": 20, "p": "0.2"}]}
        assert [t for t, _ in parsing.history_points(payload)] == [10, 20, 30]

    def test_an_unusable_point_is_dropped_rather_than_taking_the_series_down(self) -> None:
        payload = {"history": [{"t": 10, "p": "0.1"}, {"t": None, "p": "0.2"}, "nonsense"]}
        assert parsing.history_points(payload) == [(10, Decimal("0.1"))]

    def test_an_empty_series_is_empty_not_an_error(self) -> None:
        # Measured: four of five recently resolved markets answer with exactly this.
        assert parsing.history_points({"history": []}) == []

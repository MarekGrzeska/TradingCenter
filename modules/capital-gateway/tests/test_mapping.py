"""Mapping tested against recorded payloads alone — no client, no mock, no socket."""

from __future__ import annotations

from capital_gateway import mapping
from capital_gateway.dtos import AssetClass, Direction, OrderStatus, OrderType, Resolution
from tests.conftest import load_fixture


def test_a_market_becomes_an_instrument() -> None:
    gold = load_fixture("search_gold.json")["markets"][0]
    i = mapping.instrument_from_market(gold)
    assert i.symbol == "GOLD"
    assert i.asset_class is AssetClass.COMMODITIES
    assert i.tradeable is True
    # The provider calls the ask "offer"; nothing above this layer should have to know.
    assert i.ask == gold["offer"]


def test_market_details_carry_the_deposit_and_the_size_rules() -> None:
    terms = mapping.instrument_terms_from_details("GOLD", load_fixture("market_gold.json"))
    assert terms.symbol == "GOLD"
    assert terms.currency == "USD"
    assert terms.lot_size == 1
    # The number and its unit travel together — 100 alone says nothing about whether it
    # is a percentage of the contract or a multiplier over it.
    assert terms.margin_factor == 100
    assert terms.margin_factor_unit == "PERCENTAGE"
    assert (terms.min_deal_size, terms.max_deal_size, terms.size_increment) == (0.01, 50000, 0.01)


def test_market_details_carry_no_price() -> None:
    terms = mapping.instrument_terms_from_details("GOLD", load_fixture("market_gold.json"))
    assert not any(field.endswith(("bid", "ask", "price")) for field in terms.model_dump())


def test_a_rule_the_provider_omits_stays_missing_rather_than_becoming_zero() -> None:
    terms = mapping.instrument_terms_from_details("SPARSE", load_fixture("market_sparse.json"))
    assert terms.min_deal_size == 0.1
    assert terms.max_deal_size is None
    assert terms.size_increment is None
    assert terms.margin_factor is None
    assert terms.margin_factor_unit is None
    assert terms.lot_size is None


def test_market_details_without_dealing_rules_at_all() -> None:
    terms = mapping.instrument_terms_from_details("X", {"instrument": {"currency": "USD"}})
    assert terms.currency == "USD"
    assert terms.min_deal_size is None


def test_an_unknown_instrument_type_is_other_not_a_crash() -> None:
    assert mapping.asset_class("BONDS_THE_PROVIDER_ADDED_LATER") is AssetClass.OTHER
    assert mapping.asset_class(None) is AssetClass.OTHER


def test_candles_take_the_bid_side() -> None:
    raw = load_fixture("prices_gold.json")["prices"][0]
    c = mapping.candle_from_price(raw, Resolution.MINUTE)

    assert c.open == raw["openPrice"]["bid"]
    assert c.close == raw["closePrice"]["bid"]
    # Not the midpoint, and not the ask: the stream publishes bid, so any other choice
    # puts a half-spread step at the seam between history and live data.
    assert c.high != (raw["highPrice"]["bid"] + raw["highPrice"]["ask"]) / 2


def test_history_and_the_stream_read_the_same_price_side() -> None:
    """The seam. Both halves are mapped from one payload and must land on the same number: a
    midpoint on either side puts a half-spread step where history joins live candles."""
    raw = load_fixture("prices_gold.json")["prices"][0]

    from_history = mapping.candle_from_price(raw, Resolution.MINUTE)
    # What the stream publishes for the same candle: capital.com's `classic` OHLC event
    # carries one side, and upstream keeps `priceType: "bid"`.
    from_stream_close = raw["closePrice"]["bid"]

    assert from_history.close == from_stream_close


def test_a_candle_timestamp_says_it_is_utc() -> None:
    raw = load_fixture("prices_gold.json")["prices"][0]
    c = mapping.candle_from_price(raw, Resolution.MINUTE)
    # The provider sends 2026-07-23T14:19:00 with no zone, which most parsers read as
    # local time.
    assert c.ts == f"{raw['snapshotTimeUTC']}Z"


def test_a_price_with_only_one_side_still_yields_a_candle() -> None:
    c = mapping.candle_from_price(
        {"snapshotTimeUTC": "2026-07-23T14:19:00", "openPrice": {"ask": 10.0}},
        Resolution.MINUTE,
    )
    assert c.open == 10.0
    assert c.close is None


def test_an_account_flattens_its_balance() -> None:
    raw = load_fixture("accounts.json")["accounts"][0]
    a = mapping.account_from_raw(raw, active=True)
    assert a.id == raw["accountId"]
    assert a.balance == raw["balance"]["balance"]
    assert a.pnl == raw["balance"]["profitLoss"]
    assert a.active is True


def test_a_position_row_merges_position_and_market() -> None:
    row = load_fixture("positions.json")["positions"][0]
    p = mapping.position_from_raw(row)
    # The id comes from the position, the symbol from the market beside it.
    assert p.id == row["position"]["dealId"]
    assert p.symbol == row["market"]["epic"]
    assert p.direction in (Direction.BUY, Direction.SELL)


def test_a_working_order_row_reads_its_type_and_level() -> None:
    row = load_fixture("working_orders.json")["workingOrders"][0]
    w = mapping.working_order_from_raw(row)
    assert w.id == row["workingOrderData"]["dealId"]
    assert w.order_type in (OrderType.LIMIT, OrderType.STOP)
    assert w.level == row["workingOrderData"]["orderLevel"]


def test_an_accepted_confirm_takes_the_status_of_its_action() -> None:
    confirm = load_fixture("confirm_open.json")
    assert mapping.order_from_confirm(confirm).status is OrderStatus.FILLED
    # The same ACCEPTED payload means something different per action, which is why the
    # caller passes what accepted means rather than the mapper guessing.
    assert (
        mapping.order_from_confirm(confirm, accepted_status=OrderStatus.WORKING).status
        is OrderStatus.WORKING
    )


def test_a_close_confirm_reports_the_deal_it_affected() -> None:
    confirm = load_fixture("confirm_close.json")
    o = mapping.order_from_confirm(confirm, accepted_status=OrderStatus.CLOSED)
    assert o.status is OrderStatus.CLOSED
    if confirm.get("affectedDeals"):
        # The closing deal has its own id; the one a caller can look up afterwards is
        # the position it closed.
        assert o.id == confirm["affectedDeals"][0]["dealId"]


def test_a_non_accepted_confirm_is_rejected_and_says_why() -> None:
    o = mapping.order_from_confirm(load_fixture("confirm_rejected.json"))

    assert o.status is OrderStatus.REJECTED
    # `rejectReason`, which is what the provider actually sends. Written against an invented
    # `reason` field, this passed while every real rejection reached the caller with a null cause.
    assert o.reason == "RC_NOT_ENOUGH_MARGIN"


def test_a_rejection_keeps_its_reference() -> None:
    o = mapping.order_from_confirm(load_fixture("confirm_rejected.json"))

    # `affectedDeals` is empty on a refusal, so the id must not be taken from it — the
    # reference is all a caller has to correlate the attempt with the provider's record.
    assert o.reference == "o_041f7e8f-6318-4b3b-8e65-f1a81f4a3879"
    assert o.symbol == "US100"

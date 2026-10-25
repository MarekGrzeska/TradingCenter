"""The document a strategy is, checked before anything is saved (`strategies-documents`). Each refusal once."""

from __future__ import annotations

from strategies.document import SCHEMA_VERSION, servable, validate

from .builders import TRACKED, catalogue, document


def problems(raw) -> list[tuple[str, str]]:
    checked, found = validate(raw, catalogue(), servable(TRACKED))
    assert (checked is None) == bool(found)
    return [(p.path, p.message) for p in found]


def test_a_complete_document_passes() -> None:
    assert problems(document()) == []


def test_a_document_without_a_stop_and_without_an_exit_is_refused() -> None:
    found = problems(document(exits={"target": "entry_price + 50"}, sizing={"mode": "fixed_units", "value": 1}, limits={}))

    assert found == [("exits", "a position without a stop needs an exit: `when` or `max_bars`")]


# The operator's strategy of 25 October 2026: the first M5 bar of New York against EMA12, held to five minutes before
# the close, no stop and no target, 5% of the account as the deposit.
SESSION_STRATEGY = {
    "schema": 1, "name": "US100 — pierwsza M5 sesji NY wobec EMA12", "symbol": "US100", "timeframe": "MINUTE_5",
    "entries": [
        {"side": "long", "when": "session_bar(NEW_YORK) == 1 and close > ema(12)"},
        {"side": "short", "when": "session_bar(NEW_YORK) == 1 and close < ema(12)"},
    ],
    "exits": {"when": "minutes_to_session_close(NEW_YORK) <= 5"},
    "sizing": {"mode": "margin_fraction", "value": 0.05},
}


def test_a_session_strategy_without_a_stop_is_accepted() -> None:
    assert problems(SESSION_STRATEGY) == []


def test_without_a_stop_nothing_measured_in_r_is_accepted() -> None:
    found = problems(SESSION_STRATEGY | {
        "sizing": {"mode": "risk_fraction", "value": 0.01}, "exits": {"when": "open_r > 2"},
    })

    assert [path for path, _ in found] == ["sizing.mode", "exits.when"]
    assert all("no 1 R" in message for _, message in found)


def test_a_deposit_larger_than_the_equity_is_refused() -> None:
    assert [path for path, _ in problems(SESSION_STRATEGY | {"sizing": {"mode": "margin_fraction", "value": 1.5}})] == [
        "sizing.value"
    ]


def test_an_unknown_field_is_refused_not_dropped() -> None:
    [(path, message)] = problems(document(universe=["US100", "DE40"]))

    assert path == "universe" and "not a field" in message


def test_a_default_outside_its_range_is_refused() -> None:
    [(path, _)] = problems(document(params={"fast": {"default": 40, "min": 10, "max": 30, "step": 5}}))

    assert path == "params.fast"


def test_a_cycle_in_lets_names_both() -> None:
    found = problems(document(let={"a": "b + 1", "b": "a + 1"}))

    assert {path for path, _ in found} >= {"let.a", "let.b"}


def test_a_symbol_the_archive_does_not_collect_is_named() -> None:
    entries = document()["entries"]
    entries[0]["when"] = "close @ OIL > 1"

    assert any("OIL at HOUR" in message for _, message in problems(document(entries=entries)))


def test_the_traded_instrument_needs_its_minute_series() -> None:
    assert ("symbol", "the archive does not collect DE40 at MINUTE, and fills are settled on minutes") in problems(
        document(symbol="DE40")
    )


def test_a_resolution_the_archive_derives_from_minutes_needs_no_collection_but_a_day_does() -> None:
    assert ("US100", "HOUR_4") in servable(TRACKED)
    assert ("US100", "DAY") not in servable(TRACKED)


def test_a_document_from_a_future_schema_names_both_versions() -> None:
    [(path, message)] = problems(document(schema=SCHEMA_VERSION + 1))

    assert path == "schema" and str(SCHEMA_VERSION) in message and str(SCHEMA_VERSION + 1) in message


def test_a_market_order_with_a_price_and_a_stop_order_without_one_are_refused() -> None:
    entries = [
        {"side": "long", "when": "close > open", "order": {"type": "market", "price": "close"}},
        {"side": "short", "when": "close < open", "order": {"type": "stop"}},
    ]

    assert {path for path, _ in problems(document(entries=entries))} == {
        "entries[0].order.price", "entries[1].order.price",
    }


def test_the_same_strategy_written_in_another_key_order_is_one_hash() -> None:
    first, _ = validate(document(), catalogue(), servable(TRACKED))
    second, _ = validate(dict(reversed(list(document().items()))), catalogue(), servable(TRACKED))

    assert first is not None and second is not None and first.hash == second.hash


def test_a_future_schema_written_as_a_float_or_text_is_still_refused() -> None:
    assert [path for path, _ in problems(document(schema=2.0))] == ["schema"]
    assert [path for path, _ in problems(document(schema="2"))] == ["schema"]


def test_an_infinite_number_is_refused_before_it_could_reach_the_database() -> None:
    assert [path for path, _ in problems(document(sizing={"mode": "risk_fraction", "value": float("inf")}))] == [
        "sizing.value"
    ]


def test_a_parameter_no_formula_could_read_is_refused() -> None:
    found = problems(document(params={"ｆａｓｔ": {"default": 20, "min": 10, "max": 30, "step": 5}}))

    assert ("params.ｆａｓｔ", "`ｆａｓｔ` cannot name a parameter: no formula could read it as p.ｆａｓｔ") in found


def test_a_let_refused_where_it_is_defined_is_not_refused_again_where_it_is_used() -> None:
    entries = document()["entries"]
    entries[0]["when"] = "broken > 1"

    lets = document()["let"] | {"broken": "1 if close > 1 else close > 2"}

    found = problems(document(let=lets, entries=entries))

    assert [path for path, _ in found] == ["let.broken"]


def test_a_time_name_read_under_at_needs_that_instrument_in_the_archive() -> None:
    entries = document()["entries"]
    entries[0]["when"] = "hour @ OIL >= 9"

    assert any("OIL at HOUR" in message for _, message in problems(document(entries=entries)))


def test_a_session_function_on_a_daily_axis_is_refused() -> None:
    entries = document()["entries"]
    entries[0]["when"] = "session_bar(NEW_YORK) @ DAY == 1"

    found = problems(document(entries=entries))

    assert any(path == "entries[0].when" and "holds a whole session" in message for path, message in found)

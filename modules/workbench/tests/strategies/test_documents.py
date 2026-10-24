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


def test_a_document_without_a_stop_is_refused_because_of_r() -> None:
    exits = document()["exits"]
    del exits["stop"]

    assert problems(document(exits=exits)) == [("exits.stop", "a strategy needs a stop: it is what 1 R measures")]


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

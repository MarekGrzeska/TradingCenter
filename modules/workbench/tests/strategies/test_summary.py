"""The document read back from the document alone (`strategies-documents`, design D4)."""

from __future__ import annotations

from strategies import vocabulary as v
from strategies.summary import summarize

from .builders import document


def _said(doc: dict) -> str:
    summary = summarize(doc)
    assert summary is not None
    return "\n".join(line for section in summary["sections"] for line in section["lines"])


def test_every_name_and_function_of_the_language_has_a_phrase() -> None:
    names = {*v.SERIES, *v.TIME, *v.CONSTANTS, *v.SESSIONS, *v.POSITION, *v.HISTORY}

    assert names <= set(v.NAME_PHRASES)
    assert [fn.name for fn in v.FUNCTIONS.values() if not fn.phrase] == []


def test_another_interval_is_named_the_way_the_terminal_names_it() -> None:
    said = _said(document())

    assert "EMA(20) na h4 powyżej EMA(50) na h4" in said and "HOUR_4" not in said


def test_an_hour_of_the_language_is_utc_with_the_hours_in_poland() -> None:
    said = _said(document())

    assert "w piątek i od 18:00 UTC, czyli 19:00 zimą i 20:00 latem w Polsce" in said


def test_the_authors_assumptions_are_given_word_for_word() -> None:
    summary = summarize(document(notes="Sesja azjatycka to 00:00–07:00 UTC."))

    assert summary is not None and summary["notes"] == "Sesja azjatycka to 00:00–07:00 UTC."


def test_the_same_document_is_always_the_same_summary() -> None:
    assert summarize(document()) == summarize(document())


def test_arithmetic_keeps_only_the_parentheses_it_needs() -> None:
    said = _said(document(exits={"stop": "entry_price - (2 * atr(14) - 1)", "target": "(high - low) * 2"}))

    assert "Stop: cena wejścia − (2 × ATR(14) − 1)." in said and "Cel: (maksimum − minimum) × 2." in said


def test_a_variable_is_said_as_what_it_is_not_by_its_name() -> None:
    said = _said(document(let={"fast": "ema(10)", "risk": "1.5 * atr(14)"}, exits={"stop": "entry_price - risk"},
                          entries=[{"side": "long", "when": "crosses_above(fast, ema(30))", "order": {"type": "market"}}]))

    # Still listed under its name, so the summary can be held against the document.
    assert "«fast» = EMA(10)." in said and "Long, gdy EMA(10) przecina od dołu EMA(30)." in said
    assert "Stop: cena wejścia − (1,5 × ATR(14))." in said


def test_a_session_is_said_with_its_hours_in_its_city_and_in_poland_and_without_holidays() -> None:
    entries = [{"side": "long", "when": "session_bar(NEW_YORK) == 1"}]
    exits = document()["exits"] | {"when": "minutes_to_session_close(NEW_YORK) <= 5"}

    said = _said(document(entries=entries, exits=exits))

    assert "Long, gdy pierwsza świeca sesji nowojorskiej (9:30–16:00 w Nowym Jorku, zwykle 15:30–22:00 w Polsce)" in said
    assert "od 5 min przed zamknięciem sesji nowojorskiej" in said and "bez świąt giełdowych" in said


def test_a_strategy_without_a_stop_says_so_and_names_its_deposit() -> None:
    said = _said(document(
        exits={"when": "minutes_to_session_close(NEW_YORK) <= 5"}, limits={},
        sizing={"mode": "margin_fraction", "value": 0.05},
    ))

    assert "Bez stopu" in said and "Depozyt 5% kapitału na pozycję" in said

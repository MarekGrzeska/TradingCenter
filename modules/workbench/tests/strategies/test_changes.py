"""What one revision changed against another, by path (`strategies-documents`, design D5)."""

from __future__ import annotations

from strategies.changes import between

from .builders import document


def test_a_changed_stop_is_one_change_at_its_path() -> None:
    before = document()
    after = document(exits=before["exits"] | {"stop": "entry_price - 1.5 * at_entry(atr(14))"})

    assert [c.as_dict() for c in between(before, after)] == [{
        "path": "exits.stop", "kind": "changed",
        "before": "entry_price - 2 * at_entry(atr(14))", "after": "entry_price - 1.5 * at_entry(atr(14))",
    }]


def test_the_order_of_keys_is_not_a_change() -> None:
    before = document()

    assert between(before, dict(reversed(list(before.items())))) == []


def test_added_and_removed_fields_and_entries_say_so() -> None:
    before = document()
    second = {"side": "short", "when": "close < low[1]"}
    after = document(entries=[*before["entries"], second], limits={"daily_stop_r": -2})

    found = {(c.path, c.kind) for c in between(before, after)}

    assert found == {("entries[1]", "added"), ("limits.no_entry", "removed")}

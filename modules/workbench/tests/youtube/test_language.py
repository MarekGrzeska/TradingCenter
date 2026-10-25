"""A topic's or a channel's language, as the Data API takes it — the rule that stopped eight topics answering 400."""

from __future__ import annotations

import pytest

from youtube_data.watchlist import WatchlistRefused, language_code


@pytest.mark.parametrize(("given", "stored"), [("", ""), ("  ", ""), ("pl", "pl"), ("EN", "en"), ("pl-PL", "pl"), ("en_US", "en")])
def test_a_language_is_stored_as_its_two_letter_code(given, stored) -> None:
    assert language_code(given) == stored


@pytest.mark.parametrize("given", ["Polish", "English", "polski", "p", "123"])
def test_a_language_named_rather_than_coded_is_refused_with_the_form_that_works(given) -> None:
    with pytest.raises(WatchlistRefused, match="ISO 639-1.*'pl'"):
        language_code(given)

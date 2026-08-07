"""The forming candle in isolation — no socket, no hub, no provider."""

from __future__ import annotations

import pytest

from capital_gateway.dtos import Resolution
from capital_gateway.stream.forming import Bar, FormingCandle

# 2026-07-23T14:00:00Z, a clean five-minute boundary.
BASE_MS = 1_784_988_000_000
BASE_S = BASE_MS // 1000


def test_the_first_quote_opens_a_candle() -> None:
    f = FormingCandle(Resolution.MINUTE_5)

    bar = f.on_quote(BASE_MS, 100.0)

    assert bar == Bar(time=BASE_S, open=100.0, high=100.0, low=100.0, close=100.0)


def test_later_quotes_stretch_the_range_and_move_the_close() -> None:
    f = FormingCandle(Resolution.MINUTE_5)
    f.on_quote(BASE_MS, 100.0)

    f.on_quote(BASE_MS + 1_000, 103.0)
    f.on_quote(BASE_MS + 2_000, 98.0)
    bar = f.on_quote(BASE_MS + 3_000, 101.0)

    # The open is the first price seen, not the latest.
    assert bar == Bar(time=BASE_S, open=100.0, high=103.0, low=98.0, close=101.0)


def test_a_quote_in_the_next_period_opens_a_new_candle() -> None:
    f = FormingCandle(Resolution.MINUTE_5)
    f.on_quote(BASE_MS, 100.0)

    bar = f.on_quote(BASE_MS + 300_000, 105.0)

    assert bar.time == BASE_S + 300
    assert bar.open == bar.high == bar.low == bar.close == 105.0


def test_a_quote_lands_in_the_period_it_belongs_to_not_the_one_it_arrived_in() -> None:
    f = FormingCandle(Resolution.MINUTE_5)

    # 14:03:20 belongs to the candle that opened at 14:00.
    bar = f.on_quote(BASE_MS + 200_000, 100.0)

    assert bar.time == BASE_S


def test_a_sealed_candle_overwrites_what_was_assembled() -> None:
    f = FormingCandle(Resolution.MINUTE_5)
    # This module only saw the market from here, so its range is too narrow.
    f.on_quote(BASE_MS, 100.0)
    f.on_quote(BASE_MS + 1_000, 101.0)

    sealed = Bar(time=BASE_S, open=95.0, high=110.0, low=94.0, close=99.0)
    f.on_sealed(sealed)

    # The provider watched the whole period; its numbers win.
    assert f.current == sealed


def test_a_quote_after_a_sealed_candle_continues_from_it() -> None:
    f = FormingCandle(Resolution.MINUTE_5)
    f.on_sealed(Bar(time=BASE_S, open=95.0, high=110.0, low=94.0, close=99.0))

    bar = f.on_quote(BASE_MS + 1_000, 111.0)

    # Same period, so the sealed range is extended rather than restarted.
    assert bar.time == BASE_S
    assert bar.open == 95.0
    assert bar.high == 111.0


@pytest.mark.parametrize("resolution", [Resolution.DAY, Resolution.WEEK])
def test_a_session_bound_resolution_never_guesses_a_boundary(resolution: Resolution) -> None:
    f = FormingCandle(resolution)

    # Nothing to extend yet, and no arithmetic boundary worth trusting: a daily candle
    # starts at the venue's session open, not at UTC midnight.
    assert f.on_quote(BASE_MS, 100.0) is None

    f.on_sealed(Bar(time=BASE_S, open=100.0, high=100.0, low=100.0, close=100.0))
    # A day later — still folded into the last known candle, because only the provider
    # knows where the session ended.
    bar = f.on_quote(BASE_MS + 86_400_000, 120.0)

    assert bar.time == BASE_S
    assert bar.high == 120.0


def test_an_out_of_order_quote_does_not_rewind_the_candle() -> None:
    f = FormingCandle(Resolution.MINUTE_5)
    f.on_quote(BASE_MS + 300_000, 105.0)

    # A quote from the previous period arriving late: it must not reopen a candle that
    # has already moved on, which would send a chart backwards.
    bar = f.on_quote(BASE_MS, 100.0)

    assert bar.time == BASE_S + 300
    assert bar.low == 100.0

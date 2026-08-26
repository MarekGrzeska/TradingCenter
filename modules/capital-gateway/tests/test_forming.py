"""The forming candle in isolation — no socket, no hub, no provider."""

from __future__ import annotations

import pytest

from capital_gateway.dtos import Resolution
from capital_gateway.stream.forming import (
    BUCKET_SECONDS,
    NOMINAL_SECONDS,
    Bar,
    FormingCandle,
)

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
    assert f.needs_boundary is True


@pytest.mark.parametrize("resolution", [Resolution.DAY, Resolution.WEEK])
def test_a_seeded_period_takes_quotes_without_any_arithmetic(resolution: Resolution) -> None:
    """The boundary comes from the provider, and from there the folding is the same as
    everywhere else."""
    f = FormingCandle(resolution)
    f.seed(Bar(time=BASE_S, open=100.0, high=100.0, low=100.0, close=100.0))

    assert f.needs_boundary is False
    bar = f.on_quote(BASE_MS + 3_600_000, 120.0)

    assert bar is not None
    assert bar.time == BASE_S
    assert bar.high == 120.0
    assert bar.close == 120.0


@pytest.mark.parametrize("resolution", [Resolution.DAY, Resolution.WEEK])
def test_a_sealed_candle_is_never_stretched_into_the_next_period(
    resolution: Resolution,
) -> None:
    """The defect this replaced: a sealed daily candle absorbed every quote that followed, so a
    chart got yesterday's candle carrying today's high — marked forming, and undetectably wrong."""
    f = FormingCandle(resolution)
    f.seed(Bar(time=BASE_S, open=100.0, high=100.0, low=100.0, close=100.0))
    sealed = f.on_sealed(Bar(time=BASE_S, open=100.0, high=105.0, low=99.0, close=104.0))

    assert f.needs_boundary is True
    assert f.on_quote(BASE_MS + 86_400_000, 120.0) is None
    assert sealed.high == 105.0
    assert f.current == sealed


@pytest.mark.parametrize("resolution", [Resolution.DAY, Resolution.WEEK])
def test_a_break_in_the_feed_forgets_where_the_period_starts(resolution: Resolution) -> None:
    """The period may roll over while nobody is watching, so the bar in hand is no longer
    known to be the one quotes belong to."""
    f = FormingCandle(resolution)
    f.seed(Bar(time=BASE_S, open=100.0, high=100.0, low=100.0, close=100.0))

    f.invalidate()

    assert f.needs_boundary is True
    assert f.on_quote(BASE_MS + 1_000, 101.0) is None


def test_a_fixed_period_resolution_never_needs_a_boundary() -> None:
    f = FormingCandle(Resolution.MINUTE_5)
    assert f.needs_boundary is False

    f.on_sealed(Bar(time=BASE_S, open=100.0, high=100.0, low=100.0, close=100.0))
    f.invalidate()

    assert f.needs_boundary is False
    assert f.on_quote(BASE_MS + 300_000, 110.0) is not None


def test_an_out_of_order_quote_does_not_rewind_the_candle() -> None:
    f = FormingCandle(Resolution.MINUTE_5)
    f.on_quote(BASE_MS + 300_000, 105.0)

    # A quote from the previous period arriving late: it must not reopen a candle that
    # has already moved on, which would send a chart backwards.
    bar = f.on_quote(BASE_MS, 100.0)

    assert bar.time == BASE_S + 300
    assert bar.low == 100.0


@pytest.mark.parametrize("resolution", [Resolution.DAY, Resolution.WEEK])
def test_a_break_and_a_seal_are_told_apart(resolution: Resolution) -> None:
    """Both leave the module needing a boundary and need different answers to the same question.
    After a seal the same period is no use; after a break it is the confirmation being asked for."""
    f = FormingCandle(resolution)
    f.seed(Bar(time=BASE_S, open=100.0, high=100.0, low=100.0, close=100.0))

    f.invalidate()
    assert f.needs_boundary is True
    assert f.period_is_over is False

    f.on_sealed(Bar(time=BASE_S, open=100.0, high=100.0, low=100.0, close=100.0))
    assert f.needs_boundary is True
    assert f.period_is_over is True


# Measured 24 August 2026: every weekly room held a bar opened on the 17th and folded the 24th's
# quotes into it, because the provider's seal never arrived and only a seal moved the boundary.


@pytest.mark.parametrize(
    ("resolution", "period"), [(Resolution.DAY, 86_400), (Resolution.WEEK, 604_800)]
)
def test_a_quote_a_whole_period_later_does_not_stretch_the_bar(
    resolution: Resolution, period: int
) -> None:
    f = FormingCandle(resolution)
    f.seed(Bar(time=BASE_S, open=100.0, high=100.0, low=100.0, close=100.0))

    assert f.on_quote(BASE_MS + period * 1_000, 120.0) is None
    # Not published, and not silently kept either: the boundary is now the provider's to
    # give again.
    assert f.needs_boundary is True
    assert f.current is not None
    assert f.current.high == 100.0


@pytest.mark.parametrize(
    ("resolution", "period"), [(Resolution.DAY, 86_400), (Resolution.WEEK, 604_800)]
)
def test_a_quote_inside_the_nominal_period_still_stretches_the_bar(
    resolution: Resolution, period: int
) -> None:
    """The bound overstates elapsed time on purpose, so everything under it is left alone. Read as
    a boundary rather than a ceiling it would cut the candle at the wrong moment."""
    f = FormingCandle(resolution)
    f.seed(Bar(time=BASE_S, open=100.0, high=100.0, low=100.0, close=100.0))

    bar = f.on_quote(BASE_MS + (period - 1) * 1_000, 120.0)

    assert bar is not None
    assert bar.time == BASE_S
    assert bar.high == 120.0


def test_the_nominal_length_is_never_a_boundary_to_floor_by() -> None:
    """`NOMINAL_SECONDS` answers "has this period certainly ended", `BUCKET_SECONDS` "where does it
    start" — and a daily boundary computed from UTC midnight looks right and is wrong."""
    assert Resolution.DAY not in BUCKET_SECONDS
    assert Resolution.WEEK not in BUCKET_SECONDS
    assert set(NOMINAL_SECONDS) == set(BUCKET_SECONDS) | {Resolution.DAY, Resolution.WEEK}
    assert FormingCandle(Resolution.DAY).boundary_comes_from_provider is True
    assert FormingCandle(Resolution.MINUTE_5).boundary_comes_from_provider is False


@pytest.mark.parametrize("resolution", [Resolution.DAY, Resolution.WEEK])
def test_a_bar_this_module_assembled_is_never_the_providers_sealed_one(
    resolution: Resolution,
) -> None:
    """A period can now end without a seal, so "over" and "sealed" have to stay separable —
    otherwise the room's own assembly of an unfinished period lands in an archive as settled."""
    f = FormingCandle(resolution)
    f.seed(Bar(time=BASE_S, open=100.0, high=100.0, low=100.0, close=100.0))
    assert f.held_is_sealed is False

    f.on_quote(BASE_MS + NOMINAL_SECONDS[resolution] * 1_000, 120.0)

    assert f.period_is_over is True
    assert f.held_is_sealed is False

    f.on_sealed(Bar(time=BASE_S, open=100.0, high=105.0, low=99.0, close=104.0))

    assert f.held_is_sealed is True

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest

from market_data.coverage import (
    Absence,
    absence_at,
    clear_history_boundary,
    earliest_reachable,
    is_covered,
    read_coverage,
    record_coverage,
)
from market_data.db import asyncpg_dsn
from market_data.models import Resolution

pytestmark = pytest.mark.db

MOMENT = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
PAIR = ("US100", Resolution.MINUTE)


def at(minutes: int) -> datetime:
    return MOMENT + timedelta(minutes=minutes)


# --- 4.4: written and read back -----------------------------------------------------


async def test_a_recorded_range_reads_back(db: asyncpg.Connection) -> None:
    await record_coverage(db, *PAIR, at(0), at(60))

    [covered] = await read_coverage(db, *PAIR)
    assert (covered.range_start, covered.range_end) == (at(0), at(60))
    assert covered.history_ended is False


async def test_ranges_read_back_oldest_first(db: asyncpg.Connection) -> None:
    await record_coverage(db, *PAIR, at(120), at(180))
    await record_coverage(db, *PAIR, at(0), at(60))

    assert [c.range_start for c in await read_coverage(db, *PAIR)] == [at(0), at(120)]


async def test_a_pair_that_was_never_collected_has_no_coverage(db: asyncpg.Connection) -> None:
    assert await read_coverage(db, *PAIR) == []


async def test_coverage_is_kept_per_pair(db: asyncpg.Connection) -> None:
    await record_coverage(db, "US100", Resolution.MINUTE, at(0), at(60))

    assert await read_coverage(db, "US100", Resolution.HOUR) == []
    assert await read_coverage(db, "GOLD", Resolution.MINUTE) == []


async def test_a_range_that_ends_before_it_starts_is_refused(db: asyncpg.Connection) -> None:
    with pytest.raises(ValueError, match="cannot end before"):
        await record_coverage(db, *PAIR, at(60), at(0))


async def test_a_naive_bound_is_refused(db: asyncpg.Connection) -> None:
    # Stored as an instant, so a wall clock with no zone is not a coverage bound.
    with pytest.raises(ValueError, match="naive"):
        await record_coverage(db, *PAIR, datetime(2026, 8, 7, 12, 0), at(60))  # noqa: DTZ001


# --- 4.4: merging, so the table does not grow a row per fill ------------------------


async def test_two_overlapping_fills_become_one_range(db: asyncpg.Connection) -> None:
    await record_coverage(db, *PAIR, at(0), at(60))
    await record_coverage(db, *PAIR, at(30), at(90))

    [covered] = await read_coverage(db, *PAIR)
    assert (covered.range_start, covered.range_end) == (at(0), at(90))


async def test_two_fills_meeting_end_to_end_become_one_range(db: asyncpg.Connection) -> None:
    # Touching counts as merging. Otherwise a pair collected nightly accumulates a row a
    # night, and "is this moment covered" becomes a walk through all of them.
    await record_coverage(db, *PAIR, at(0), at(60))
    await record_coverage(db, *PAIR, at(60), at(120))

    [covered] = await read_coverage(db, *PAIR)
    assert (covered.range_start, covered.range_end) == (at(0), at(120))


async def test_a_fill_inside_what_is_already_covered_widens_nothing(
    db: asyncpg.Connection,
) -> None:
    await record_coverage(db, *PAIR, at(0), at(120))
    await record_coverage(db, *PAIR, at(30), at(60))

    [covered] = await read_coverage(db, *PAIR)
    assert (covered.range_start, covered.range_end) == (at(0), at(120))


async def test_a_fill_bridging_two_ranges_joins_all_three(db: asyncpg.Connection) -> None:
    await record_coverage(db, *PAIR, at(0), at(30))
    await record_coverage(db, *PAIR, at(90), at(120))
    await record_coverage(db, *PAIR, at(20), at(100))

    [covered] = await read_coverage(db, *PAIR)
    assert (covered.range_start, covered.range_end) == (at(0), at(120))


async def test_a_gap_between_fills_stays_a_gap(db: asyncpg.Connection) -> None:
    # The whole point of the record: an hour nobody looked at must not be swallowed by
    # the two hours on either side of it.
    await record_coverage(db, *PAIR, at(0), at(60))
    await record_coverage(db, *PAIR, at(120), at(180))

    assert [(c.range_start, c.range_end) for c in await read_coverage(db, *PAIR)] == [
        (at(0), at(60)),
        (at(120), at(180)),
    ]


async def test_two_fills_recording_at_the_same_moment_still_leave_one_range(
    db: asyncpg.Connection, migrated_url: str
) -> None:
    # Recording a range is read-then-write, and the second writer's rows do not exist yet
    # for a row lock to catch. Without the lock on the pair, both of these read an empty
    # table, both insert, and the pair is left with two ranges that should have been one.
    other = await asyncpg.connect(asyncpg_dsn(migrated_url))
    try:
        await asyncio.gather(
            record_coverage(db, *PAIR, at(0), at(60)),
            record_coverage(other, *PAIR, at(60), at(120)),
        )
    finally:
        await other.close()

    [covered] = await read_coverage(db, *PAIR)
    assert (covered.range_start, covered.range_end) == (at(0), at(120))


async def test_recording_returns_the_range_as_it_now_stands(db: asyncpg.Connection) -> None:
    await record_coverage(db, *PAIR, at(0), at(60))

    merged = await record_coverage(db, *PAIR, at(30), at(90))

    assert (merged.range_start, merged.range_end) == (at(0), at(90))


# --- 4.4: the boundary that follows from history_ended ------------------------------


async def test_the_end_of_provider_history_is_remembered(db: asyncpg.Connection) -> None:
    # The boundary lies where the read ran out, which is not the edge the read asked
    # about: a window from at(0) that came back with nothing older than at(20) proves
    # something about at(20) and nothing about at(0).
    await record_coverage(db, *PAIR, at(0), at(60), history_ended=True, history_ends_at=at(20))

    assert await earliest_reachable(db, *PAIR) == at(20)


async def test_a_boundary_must_say_where_it_lies(db: asyncpg.Connection) -> None:
    """Refused rather than defaulted. A boundary placed at the requested edge announces
    as measured a stretch nobody looked at, and it is then kept and acted on."""
    with pytest.raises(ValueError, match="where it lies"):
        await record_coverage(db, *PAIR, at(0), at(60), history_ended=True)


async def test_a_pair_that_has_not_reached_the_end_has_no_boundary(
    db: asyncpg.Connection,
) -> None:
    # None means "not known yet", not "there is no limit" — the difference decides
    # whether backfill keeps reaching further back.
    await record_coverage(db, *PAIR, at(0), at(60))

    assert await earliest_reachable(db, *PAIR) is None


async def test_the_boundary_survives_a_later_merge(db: asyncpg.Connection) -> None:
    # Nothing can be older than it: a range starting before the provider's own first
    # candle is not something a backfill can produce.
    await record_coverage(db, *PAIR, at(0), at(60), history_ended=True, history_ends_at=at(20))
    await record_coverage(db, *PAIR, at(30), at(120))

    [covered] = await read_coverage(db, *PAIR)
    assert covered.history_ended is True
    assert await earliest_reachable(db, *PAIR) == at(20)


async def test_a_merge_does_not_drag_the_boundary_down_to_the_range_start(
    db: asyncpg.Connection,
) -> None:
    """The defect this column replaced.

    The boundary used to be read off `range_start`, and ranges merge — so a range meeting
    an older one end to end produced one row starting at the older edge, and the boundary
    slid there with it. On US100 that put "the provider has nothing before this" at the
    earliest moment the pair had ever verified.
    """
    await record_coverage(db, *PAIR, at(60), at(120), history_ended=True, history_ends_at=at(80))
    await record_coverage(db, *PAIR, at(0), at(70))

    [covered] = await read_coverage(db, *PAIR)
    assert covered.range_start == at(0)
    assert covered.history_ends_at == at(80)
    assert await earliest_reachable(db, *PAIR) == at(80)


async def test_the_deeper_of_two_boundaries_wins_a_merge(db: asyncpg.Connection) -> None:
    """Two can only disagree by one having been measured when the provider held less, and
    the earlier one is the one that was demonstrated."""
    await record_coverage(db, *PAIR, at(60), at(120), history_ended=True, history_ends_at=at(80))
    await record_coverage(db, *PAIR, at(0), at(70), history_ended=True, history_ends_at=at(10))

    assert await earliest_reachable(db, *PAIR) == at(10)


async def test_a_deeper_request_drops_the_boundary_and_keeps_the_coverage(
    db: asyncpg.Connection,
) -> None:
    """No candle and no verified range is given up — only the claim that there is nothing
    below. Deleting the pair used to be the only way to retract it."""
    await record_coverage(db, *PAIR, at(0), at(120), history_ended=True, history_ends_at=at(20))

    dropped = await clear_history_boundary(db, *PAIR)

    assert dropped == at(20)
    assert await earliest_reachable(db, *PAIR) is None
    [covered] = await read_coverage(db, *PAIR)
    assert (covered.range_start, covered.range_end) == (at(0), at(120))
    assert covered.history_ended is False


async def test_dropping_a_boundary_that_is_not_there_is_not_an_error(
    db: asyncpg.Connection,
) -> None:
    await record_coverage(db, *PAIR, at(0), at(120))

    assert await clear_history_boundary(db, *PAIR) is None


async def test_a_pair_keeps_one_boundary_after_merging(db: asyncpg.Connection) -> None:
    # Two would be two answers to how far back there is anything left to fetch. The
    # partial unique index refuses them; merging has to not produce them in the first
    # place.
    await record_coverage(db, *PAIR, at(0), at(60), history_ended=True, history_ends_at=at(10))
    await record_coverage(db, *PAIR, at(50), at(120), history_ended=True, history_ends_at=at(55))

    covered = await read_coverage(db, *PAIR)
    assert len(covered) == 1
    assert covered[0].history_ended is True


# --- 4.5 and 4.6: the two kinds of absence ------------------------------------------


async def test_a_moment_inside_coverage_is_covered(db: asyncpg.Connection) -> None:
    await record_coverage(db, *PAIR, at(0), at(60))

    assert await is_covered(db, *PAIR, at(30)) is True


async def test_the_edges_of_a_range_are_inside_it(db: asyncpg.Connection) -> None:
    await record_coverage(db, *PAIR, at(0), at(60))

    assert await is_covered(db, *PAIR, at(0)) is True
    assert await is_covered(db, *PAIR, at(60)) is True


async def test_a_moment_outside_every_range_is_not_covered(db: asyncpg.Connection) -> None:
    await record_coverage(db, *PAIR, at(0), at(60))

    assert await is_covered(db, *PAIR, at(90)) is False


async def test_a_missing_candle_inside_coverage_means_the_market_was_shut(
    db: asyncpg.Connection,
) -> None:
    await record_coverage(db, *PAIR, at(0), at(60))

    assert await absence_at(db, *PAIR, at(30)) is Absence.MARKET_CLOSED


async def test_a_missing_candle_outside_coverage_means_nobody_looked(
    db: asyncpg.Connection,
) -> None:
    await record_coverage(db, *PAIR, at(0), at(60))

    assert await absence_at(db, *PAIR, at(90)) is Absence.NOT_COLLECTED


async def test_the_two_absences_are_told_apart(db: asyncpg.Connection) -> None:
    """4.6, stated in one place.

    In the candle table these two are the same nothing: a Saturday at 3am and an
    afternoon when ingest was down both read as no row. Only one of them is worth
    sending anyone back to the provider for, and coverage is what separates them.
    """
    await record_coverage(db, *PAIR, at(0), at(60))

    inside = await absence_at(db, *PAIR, at(30))
    outside = await absence_at(db, *PAIR, at(600))

    assert inside is not outside
    assert (inside, outside) == (Absence.MARKET_CLOSED, Absence.NOT_COLLECTED)


async def test_a_gap_between_two_ranges_is_not_collected(db: asyncpg.Connection) -> None:
    # Surrounded on both sides and still nobody looked. Merging must not have papered
    # over it.
    await record_coverage(db, *PAIR, at(0), at(60))
    await record_coverage(db, *PAIR, at(120), at(180))

    assert await absence_at(db, *PAIR, at(90)) is Absence.NOT_COLLECTED


async def test_coverage_for_one_pair_says_nothing_about_another(
    db: asyncpg.Connection,
) -> None:
    await record_coverage(db, "US100", Resolution.MINUTE, at(0), at(60))

    assert await absence_at(db, "GOLD", Resolution.MINUTE, at(30)) is Absence.NOT_COLLECTED
    assert await absence_at(db, "US100", Resolution.HOUR, at(30)) is Absence.NOT_COLLECTED

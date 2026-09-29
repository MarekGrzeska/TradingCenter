"""The news statements, against a real PostgreSQL: identity is a pair, a moment of first sight never moves,
retention spares what the operator kept."""

from __future__ import annotations

import statistics
from datetime import timedelta

import pytest

from social_data.news import latency, store

from .builders import NOON, feed_item

pytestmark = pytest.mark.db

SOURCE = "a-feed"
WINDOW = (NOON - timedelta(days=1), NOON + timedelta(days=1))


async def collect(db, items, *, seen_at=NOON, source=SOURCE):
    await store.declare_sources(db, [source])
    previous = await store.previous_success(db, source)
    inserted = await store.insert_items(
        db, source, items, seen_at=seen_at, previous_fetch_at=previous
    )
    await store.record_success(db, source, at=seen_at, newest_published_at=None)
    return inserted


async def window(db, **kwargs):
    return await store.items_in_window(
        db, start=WINDOW[0], end=WINDOW[1], sources=None, text=None, limit=100, **kwargs
    )


async def test_a_headline_seen_again_is_stored_once_and_keeps_its_first_moment(db):
    first = await collect(db, [feed_item("a", title="first")])
    second = await collect(
        db,
        [feed_item("a", title="rewritten", published_at=NOON + timedelta(hours=1))],
        seen_at=NOON + timedelta(minutes=5),
    )

    [stored] = await window(db)
    assert (first, second) == (1, 0)
    assert (stored.title, stored.first_seen_at) == ("first", NOON)


async def test_two_feeds_may_carry_the_same_identifier(db):
    await collect(db, [feed_item("a")], source="one")
    await collect(db, [feed_item("a")], source="two")

    assert len(await window(db)) == 2


async def test_the_first_fetch_of_a_feed_finds_headlines_there_and_the_next_measures_them(db):
    await collect(db, [feed_item("old")], seen_at=NOON)
    await collect(db, [feed_item("old"), feed_item("new")], seen_at=NOON + timedelta(minutes=2))

    found = {item.external_id: item for item in await window(db)}
    assert found["old"].previous_fetch_at is None
    assert found["new"].previous_fetch_at == NOON


async def test_a_window_answers_newest_first_and_a_headline_without_a_time_sorts_by_first_sight(db):
    await collect(
        db,
        [
            feed_item("early", published_at=NOON - timedelta(hours=2)),
            feed_item("late", published_at=NOON - timedelta(minutes=1)),
            feed_item("undated", published_at=None),
        ],
    )

    assert [item.external_id for item in await window(db)] == ["undated", "late", "early"]


async def test_a_window_narrows_by_source_and_by_text_ignoring_case(db):
    await collect(
        db, [feed_item("a", title="IRAN talks"), feed_item("b", title="Markets")], source="one"
    )
    await collect(db, [feed_item("c", summary="the iran deal")], source="two")

    by_text = await store.items_in_window(
        db, start=WINDOW[0], end=WINDOW[1], sources=None, text="iran", limit=100
    )
    by_source = await store.items_in_window(
        db, start=WINDOW[0], end=WINDOW[1], sources=["one"], text="iran", limit=100
    )

    assert {item.external_id for item in by_text} == {"a", "c"}
    assert {item.external_id for item in by_source} == {"a"}


async def test_keeping_is_idempotent_and_touches_nothing_else(db):
    await collect(db, [feed_item("a")])
    at = NOON + timedelta(hours=1)

    kept = await store.set_kept(db, SOURCE, "a", keep=True, at=at)
    again = await store.set_kept(db, SOURCE, "a", keep=True, at=at + timedelta(hours=1))
    let_go = await store.set_kept(db, SOURCE, "a", keep=False, at=at)

    assert kept is not None and again is not None and let_go is not None
    assert again.kept_at == at
    assert let_go.kept_at is None
    assert (kept.title, kept.first_seen_at, kept.published_at) == (
        let_go.title,
        let_go.first_seen_at,
        let_go.published_at,
    )
    assert await store.set_kept(db, SOURCE, "missing", keep=True, at=at) is None


async def test_the_sweep_removes_the_old_and_spares_the_kept(db):
    await collect(db, [feed_item("old"), feed_item("old-kept")], seen_at=NOON - timedelta(days=40))
    await collect(db, [feed_item("fresh")], seen_at=NOON)
    await store.set_kept(db, SOURCE, "old-kept", keep=True, at=NOON)

    swept = await store.sweep(db, before=NOON - timedelta(days=28))

    assert swept == 1
    assert {item.external_id for item in await store.kept_items(db, limit=10)} == {"old-kept"}
    await store.set_kept(db, SOURCE, "old-kept", keep=False, at=NOON)
    assert await store.sweep(db, before=NOON - timedelta(days=28)) == 1


async def test_a_failure_moves_nothing_forward(db):
    await collect(db, [feed_item("a")])
    await store.record_failure(
        db, SOURCE, at=NOON + timedelta(minutes=5), reason="refused: HTTP 403"
    )

    [row] = await store.source_rows(db)
    assert row.last_success_at == NOON
    assert row.last_failure == "refused: HTTP 403"


def _interpolated(values, fraction):
    """The reference `percentile_cont` is held to: linear between the two nearest ranks."""
    position = (len(values) - 1) * fraction
    below = int(position)
    above = min(below + 1, len(values) - 1)
    return values[below] + (values[above] - values[below]) * (position - below)


def _headlines():
    """One of every kind a feed can produce, as (published, previous_fetch, first_seen)."""
    m = timedelta(minutes=1)
    return [
        (NOON, NOON + 3 * m, NOON + 5 * m),
        (NOON + 4 * m, NOON + 3 * m, NOON + 5 * m),
        (NOON, NOON + 1 * m, NOON + 9 * m),
        (None, NOON, NOON + 5 * m),
        (NOON, None, NOON + 5 * m),
        (NOON + 60 * m, NOON, NOON + 5 * m),
        (NOON + 6 * m, NOON, NOON + 5 * m),
    ]


async def test_a_sources_day_is_the_same_definition_as_a_headlines_delay(db):
    await store.declare_sources(db, [SOURCE])
    for n, (published, previous, seen) in enumerate(_headlines()):
        await store.insert_items(
            db,
            SOURCE,
            [feed_item(str(n), published_at=published)],
            seen_at=seen,
            previous_fetch_at=previous,
        )

    figures = (
        await store.source_figures(
            db, NOON - timedelta(days=1), tolerance_seconds=latency.CLOCK_TOLERANCE.total_seconds()
        )
    )[SOURCE]
    delays = [
        latency.delay(published_at=p, first_seen_at=s, previous_fetch_at=prev)
        for p, prev, s in _headlines()
    ]
    lowers = sorted(d.lower_seconds for d in delays if d.lower_seconds is not None)
    uppers = sorted(d.upper_seconds for d in delays if d.upper_seconds is not None)

    assert figures.items == len(delays)
    assert figures.unmeasured == sum(1 for d in delays if d.unmeasured is not None)
    assert figures.lower_median == pytest.approx(statistics.median(lowers))
    assert figures.upper_median == pytest.approx(statistics.median(uppers))
    assert figures.lower_p90 == pytest.approx(_interpolated(lowers, 0.9))
    assert figures.upper_p90 == pytest.approx(_interpolated(uppers, 0.9))


async def test_a_source_with_nothing_measured_has_empty_figures_and_the_count_of_what_it_could_not(
    db,
):
    await store.declare_sources(db, [SOURCE])
    await store.insert_items(
        db, SOURCE, [feed_item("a", published_at=None)], seen_at=NOON, previous_fetch_at=NOON
    )

    figures = (await store.source_figures(db, NOON - timedelta(days=1), tolerance_seconds=120))[
        SOURCE
    ]

    assert (figures.items, figures.unmeasured) == (1, 1)
    assert figures.lower_median is None and figures.upper_p90 is None


async def test_the_body_is_stored_beside_the_lead_and_an_empty_one_stays_empty(db):
    await collect(
        db,
        [
            feed_item("full", summary="lead", content="the whole piece\n\nin two paragraphs"),
            feed_item("short", summary="lead"),
        ],
    )

    stored = {item.external_id: item for item in await window(db)}

    assert stored["full"].content == "the whole piece\n\nin two paragraphs"
    assert stored["short"].content == ""

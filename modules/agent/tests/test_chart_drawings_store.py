"""`chart_drawings`: the four-column geometry, one `CHECK` per shape, and the round trip
through `store.py`'s three domain classes.

specs/agent-chart-drawings, "Rysunek należy do instrumentu, nie do widoku" and "Rysunki są
trwałe i mają własną tożsamość".
"""

from __future__ import annotations

from datetime import UTC, datetime

import asyncpg
import pytest

from agent import store
from agent.models import ChartLevel, ChartTrendline, ChartTrendlinePoint, ChartZone

pytestmark = pytest.mark.db


async def _session(db) -> int:
    session = await store.create_session(db, owner_principal="op-1", model_id="gpt-5.6-luna")
    return session.id


async def test_a_level_survives_the_round_trip(db) -> None:
    session_id = await _session(db)
    at = datetime(2026, 1, 3, 12, 0, tzinfo=UTC)

    [written] = await store.add_drawings(
        db,
        session_id=session_id,
        symbol="US100",
        geometries=[ChartLevel(price=21500.0, at=at, label="weekly high", color="--color-up")],
    )

    [read] = await store.list_drawings(db, symbol="US100")
    assert read.id == written.id
    assert read.symbol == "US100"
    assert read.session_id == session_id
    assert isinstance(read.geometry, ChartLevel)
    assert read.geometry.price == 21500.0
    assert read.geometry.at == at
    assert read.geometry.label == "weekly high"
    assert read.geometry.color == "--color-up"


async def test_a_level_without_a_moment_is_open_from_the_start(db) -> None:
    session_id = await _session(db)
    [written] = await store.add_drawings(
        db, session_id=session_id, symbol="US100", geometries=[ChartLevel(price=21500.0)]
    )

    [read] = await store.list_drawings(db, symbol="US100")
    assert read.id == written.id
    assert isinstance(read.geometry, ChartLevel)
    assert read.geometry.at is None


async def test_a_zone_survives_the_round_trip(db) -> None:
    session_id = await _session(db)
    start = datetime(2026, 1, 3, 0, 0, tzinfo=UTC)
    end = datetime(2026, 1, 4, 0, 0, tzinfo=UTC)

    await store.add_drawings(
        db,
        session_id=session_id,
        symbol="US100",
        geometries=[ChartZone(top=21600.0, bottom=21400.0, from_=start, to=end)],
    )

    [read] = await store.list_drawings(db, symbol="US100")
    assert isinstance(read.geometry, ChartZone)
    assert (read.geometry.top, read.geometry.bottom) == (21600.0, 21400.0)
    assert (read.geometry.from_, read.geometry.to) == (start, end)


async def test_a_zone_with_top_below_bottom_is_refused_by_the_database(db) -> None:
    session_id = await _session(db)

    with pytest.raises(asyncpg.CheckViolationError):
        await store.add_drawings(
            db,
            session_id=session_id,
            symbol="US100",
            geometries=[ChartZone(top=100.0, bottom=200.0)],
        )


async def test_a_trendline_survives_the_round_trip(db) -> None:
    session_id = await _session(db)
    a = datetime(2026, 1, 3, 0, 0, tzinfo=UTC)
    b = datetime(2026, 1, 5, 0, 0, tzinfo=UTC)

    await store.add_drawings(
        db,
        session_id=session_id,
        symbol="US100",
        geometries=[
            ChartTrendline(
                a=ChartTrendlinePoint(time=a, price=21000.0),
                b=ChartTrendlinePoint(time=b, price=21800.0),
            )
        ],
    )

    [read] = await store.list_drawings(db, symbol="US100")
    assert isinstance(read.geometry, ChartTrendline)
    assert (read.geometry.a.time, read.geometry.a.price) == (a, 21000.0)
    assert (read.geometry.b.time, read.geometry.b.price) == (b, 21800.0)


async def test_a_trendline_with_its_second_point_not_later_is_refused_by_the_database(db) -> None:
    session_id = await _session(db)
    same = datetime(2026, 1, 3, 0, 0, tzinfo=UTC)

    with pytest.raises(asyncpg.CheckViolationError):
        await store.add_drawings(
            db,
            session_id=session_id,
            symbol="US100",
            geometries=[
                ChartTrendline(
                    a=ChartTrendlinePoint(time=same, price=21000.0),
                    b=ChartTrendlinePoint(time=same, price=21800.0),
                )
            ],
        )


async def test_a_non_positive_price_is_refused_by_the_database(db) -> None:
    session_id = await _session(db)

    with pytest.raises(asyncpg.CheckViolationError):
        await store.add_drawings(
            db, session_id=session_id, symbol="US100", geometries=[ChartLevel(price=0.0)]
        )


async def test_list_only_answers_for_the_symbol_asked(db) -> None:
    session_id = await _session(db)
    await store.add_drawings(
        db, session_id=session_id, symbol="US100", geometries=[ChartLevel(price=21500.0)]
    )
    await store.add_drawings(
        db, session_id=session_id, symbol="GOLD", geometries=[ChartLevel(price=2000.0)]
    )

    assert len(await store.list_drawings(db, symbol="US100")) == 1
    assert len(await store.list_drawings(db, symbol="GOLD")) == 1
    assert await store.list_drawings(db, symbol="SILVER") == []


async def test_count_matches_what_list_would_return(db) -> None:
    session_id = await _session(db)
    await store.add_drawings(
        db,
        session_id=session_id,
        symbol="US100",
        geometries=[ChartLevel(price=21500.0), ChartLevel(price=21600.0)],
    )

    assert await store.count_drawings(db, symbol="US100") == 2


async def test_remove_deletes_only_the_ids_named(db) -> None:
    session_id = await _session(db)
    kept, removed = await store.add_drawings(
        db,
        session_id=session_id,
        symbol="US100",
        geometries=[ChartLevel(price=21500.0), ChartLevel(price=21600.0)],
    )

    actually_removed = await store.remove_drawings(db, symbol="US100", ids=[removed.id])

    assert actually_removed == [removed.id]
    remaining = await store.list_drawings(db, symbol="US100")
    assert [d.id for d in remaining] == [kept.id]


async def test_remove_ignores_an_id_belonging_to_another_symbol(db) -> None:
    session_id = await _session(db)
    [us100_level] = await store.add_drawings(
        db, session_id=session_id, symbol="US100", geometries=[ChartLevel(price=21500.0)]
    )
    await store.add_drawings(
        db, session_id=session_id, symbol="GOLD", geometries=[ChartLevel(price=2000.0)]
    )

    # Asking GOLD to remove US100's id must not touch it — the id exists, just not here.
    actually_removed = await store.remove_drawings(db, symbol="GOLD", ids=[us100_level.id])

    assert actually_removed == []
    assert len(await store.list_drawings(db, symbol="US100")) == 1


async def test_a_drawing_outlives_the_session_that_made_it(db) -> None:
    session_id = await _session(db)
    [written] = await store.add_drawings(
        db, session_id=session_id, symbol="US100", geometries=[ChartLevel(price=21500.0)]
    )

    await store.delete_session(db, session_id=session_id, owner_principal="op-1")
    # `delete_session` is a soft delete and would not exercise `ON DELETE SET NULL` on its
    # own, so the row is deleted for real here, the way an operator's account removal one
    # day might.
    await db.execute("DELETE FROM sessions WHERE id = $1", session_id)

    [read] = await store.list_drawings(db, symbol="US100")
    assert read.id == written.id
    assert read.session_id is None


async def test_update_changes_only_the_fields_given(db) -> None:
    session_id = await _session(db)
    [written] = await store.add_drawings(
        db,
        session_id=session_id,
        symbol="US100",
        geometries=[ChartLevel(price=21500.0, label="old label")],
    )

    updated = await store.update_drawing(
        db, drawing_id=written.id, price_a=21700.0, price_b=None, label=None
    )

    assert updated is not None
    assert isinstance(updated.geometry, ChartLevel)
    assert updated.geometry.price == 21700.0
    # Label untouched: `None` here means "leave it", not "clear it" — `PatchSessionIn`'s
    # own convention.
    assert updated.geometry.label == "old label"


async def test_update_of_an_unknown_id_answers_none(db) -> None:
    result = await store.update_drawing(db, drawing_id=999_999, price_a=1.0, price_b=None, label=None)
    assert result is None

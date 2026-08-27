"""One evaluation, and what it records — including when it could not see."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from builders import crossing_facts
from fakes import FakeArchive

from strategy import store
from strategy.archive import Gap
from strategy.errors import ArchiveUnreachable
from strategy.runner.loop import evaluate_all, evaluate_once

pytestmark = pytest.mark.db

BAR = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)


async def a_watch(pool, *, strategy_id: str = "baseline_ma_cross", symbol: str = "US100"):
    async with pool.acquire() as conn:
        params = await store.add_parameter_set(conn, strategy_id, {})
        return await store.put_watch(conn, strategy_id, symbol, params.id)


def crossing() -> object:
    return crossing_facts(fast=[99.0, 101.0], slow=[100.0, 100.0], atr=[2.0, 2.0])


class TestOnePass:
    async def test_a_setup_is_recorded_with_its_levels(self, pool) -> None:
        watch = await a_watch(pool)
        archive = FakeArchive(last_bar=BAR, facts=crossing())

        result = await evaluate_once(pool, archive, watch)

        assert result.decision is not None
        assert result.decision.action == "trade"
        assert result.recorded is True
        async with pool.acquire() as conn:
            recorded = await store.last_decision(conn, watch.strategy_id, watch.symbol)
        assert recorded is not None
        assert recorded.as_of == BAR
        assert recorded.decision.direction == "long"

    async def test_a_bar_already_decided_is_not_read_again(self, pool) -> None:
        """The commonest outcome by far — the loop wakes far more often than bars close —
        and it must cost one cheap query rather than a read of the archive."""
        watch = await a_watch(pool)
        archive = FakeArchive(last_bar=BAR, facts=crossing())
        await evaluate_once(pool, archive, watch)
        archive.reads.clear()

        result = await evaluate_once(pool, archive, watch)

        assert result.skipped == "already decided"
        assert [call[0] for call in archive.reads] == ["last_closed_bar"]

    async def test_a_new_bar_is_decided(self, pool) -> None:
        watch = await a_watch(pool)
        archive = FakeArchive(last_bar=BAR, facts=crossing())
        await evaluate_once(pool, archive, watch)

        archive.last_bar = BAR + timedelta(hours=1)
        archive.facts = crossing_facts(fast=[101.0, 102.0], slow=[100.0, 100.0], atr=[2.0, 2.0])
        result = await evaluate_once(pool, archive, watch)

        assert result.recorded is True
        assert result.decision is not None
        assert result.decision.action == "no_trade"


class TestWhenItCannotSee:
    async def test_an_unreachable_archive_is_recorded_rather_than_swallowed(self, pool) -> None:
        """A strategy that could not see is not a strategy that saw nothing. The operator's question three weeks later
        is "why did nothing happen", and silence is the one answer that cannot be given."""
        watch = await a_watch(pool)
        # The bar can be had; the facts cannot — so there is a bar to record against.
        archive = FakeArchive(
            last_bar=BAR,
            facts_raises=ArchiveUnreachable("the archive did not answer for indicators"),
        )

        result = await evaluate_once(pool, archive, watch)

        assert result.recorded is True
        assert result.reason_kind == "coverage"
        async with pool.acquire() as conn:
            recorded = await store.last_decision(conn, watch.strategy_id, watch.symbol)
        assert recorded is not None
        assert "did not answer" in (recorded.decision.reason or "")

    async def test_a_bar_that_cannot_be_had_is_skipped_not_recorded(self, pool) -> None:
        """A decision needs a bar to belong to. Without one there is nothing to write a row
        against, so this is a skip with a reason in the log rather than a row."""
        watch = await a_watch(pool)
        archive = FakeArchive(raises=ArchiveUnreachable("the archive did not answer"))

        result = await evaluate_once(pool, archive, watch)

        assert result.skipped is not None
        async with pool.acquire() as conn:
            assert await store.last_decision(conn, watch.strategy_id, watch.symbol) is None

    async def test_a_gap_in_the_range_refuses_the_setup(self, pool) -> None:
        watch = await a_watch(pool)
        archive = FakeArchive(
            last_bar=BAR,
            facts=crossing(),
            gaps=(Gap(start=BAR - timedelta(days=2), end=BAR - timedelta(days=1)),),
        )

        result = await evaluate_once(pool, archive, watch)

        assert result.decision is not None
        assert result.decision.action == "no_trade"
        assert result.reason_kind == "coverage"

    async def test_a_watch_for_a_strategy_this_image_lost_is_skipped(self, pool) -> None:
        """The other watches are unaffected, and the operator's remedy is a row rather than
        a restart."""
        watch = await a_watch(pool, strategy_id="a_strategy_that_left")
        archive = FakeArchive(last_bar=BAR, facts=crossing())

        result = await evaluate_once(pool, archive, watch)

        assert result.skipped is not None
        assert "a_strategy_that_left" in result.skipped


class TestEveryWatch:
    async def test_watches_are_independent(self, pool) -> None:
        """One strategy raising must not stop the others: a platform that stops watching everything because one entry
        failed fails in the least useful way."""
        await a_watch(pool, symbol="US100")
        await a_watch(pool, strategy_id="a_strategy_that_left", symbol="EURUSD")
        archive = FakeArchive(last_bar=BAR, facts=crossing())

        results = await evaluate_all(pool, archive)

        assert len(results) == 2
        recorded = [result for result in results if result.recorded]
        assert [result.watch.symbol for result in recorded] == ["US100"]

    async def test_a_deactivated_watch_is_not_evaluated(self, pool) -> None:
        watch = await a_watch(pool)
        async with pool.acquire() as conn:
            await store.set_watch_active(conn, watch.id, False)
        archive = FakeArchive(last_bar=BAR, facts=crossing())

        assert await evaluate_all(pool, archive) == []

    async def test_no_watches_at_all_is_a_supported_state(self, pool) -> None:
        """Zero is not a degraded platform; it is a platform nobody has asked anything of."""
        assert await evaluate_all(pool, FakeArchive()) == []

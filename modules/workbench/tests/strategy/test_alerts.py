"""Which decision is worth saying out loud, and what happens when saying it fails.

The loop evaluates on every closed bar, so the rule these tests hold is the one that keeps the
channel readable: a trade, and only where it is a change from the last decision for that pair.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from strategy import store
from strategy.alerts import Alerts, GatewayRefused, GatewayUnreachable, is_new_setup, message
from strategy.runner.loop import evaluate_once
from strategy.spec import Decision

from .builders import crossing_facts
from .fakes import FakeArchive

BAR = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)


class RecordingGateway:
    def __init__(self, fails: Exception | None = None) -> None:
        self._fails = fails
        self.sent: list[tuple[str, str]] = []

    async def send(self, *, destination: str, text: str) -> None:
        self.sent.append((destination, text))
        if self._fails is not None:
            raise self._fails


def _alerts(gateway) -> Alerts:
    return Alerts(gateway, destination="operator")  # type: ignore[arg-type]


async def a_watch(pool, *, strategy_id: str = "baseline_ma_cross", symbol: str = "US100"):
    async with pool.acquire() as conn:
        params = await store.add_parameter_set(conn, strategy_id, {})
        return await store.put_watch(conn, strategy_id, symbol, params.id)


def crossing() -> object:
    return crossing_facts(fast=[99.0, 101.0], slow=[100.0, 100.0], atr=[2.0, 2.0])


def flat() -> object:
    """No crossing, so the strategy refuses — the ordinary outcome of most passes."""
    return crossing_facts(fast=[99.0, 99.0], slow=[100.0, 100.0], atr=[2.0, 2.0])


def _trade(direction: str = "long") -> Decision:
    return Decision.trade(direction=direction, entry=100.0, stop=98.0, target=106.0)  # type: ignore[arg-type]


class TestWhichDecisionIsWorthSaying:
    """The rule at the layer that holds it — a pure function of the decision and the last one, so
    none of these needs a database."""

    def test_a_refusal_is_never_announced(self) -> None:
        assert is_new_setup(Decision.no_trade("no crossing"), None) is False

    def test_the_first_trade_for_a_pair_is_announced(self) -> None:
        assert is_new_setup(_trade(), None) is True

    def test_the_same_setup_standing_from_the_previous_bar_is_not_announced(self) -> None:
        previous = _recorded(_trade("long"))
        assert is_new_setup(_trade("long"), previous) is False

    def test_a_direction_that_flipped_is_a_new_setup(self) -> None:
        previous = _recorded(_trade("long"))
        assert is_new_setup(_trade("short"), previous) is True

    def test_a_trade_after_a_refusal_is_announced(self) -> None:
        previous = _recorded(Decision.no_trade("no crossing"))
        assert is_new_setup(_trade(), previous) is True

    def test_the_same_setup_is_announced_again_when_nobody_was_told(self) -> None:
        """The retry, at the layer that decides it. An unmarked previous trade means the delivery
        did not happen, so this repetition is the first notification rather than the second."""
        previous = _recorded(_trade("long"), notified_at=None)
        assert is_new_setup(_trade("long"), previous) is True


def _recorded(
    decision: Decision, *, notified_at: datetime | None = BAR
) -> store.RecordedDecision:
    """A decision as it was written down. Announced by default, because that is the ordinary state
    of the one before this — the interesting case is the other one, and it says so."""
    return store.RecordedDecision(
        id=1,
        strategy_id="baseline_ma_cross",
        symbol="US100",
        parameter_set_id=1,
        as_of=BAR,
        decision=decision,
        reason_kind=None,
        facts={},
        created_at=BAR,
        notified_at=notified_at,
    )


@pytest.mark.db
class TestThroughTheLoop:
    async def test_a_setup_is_announced_and_marked(self, pool) -> None:
        watch = await a_watch(pool)
        archive = FakeArchive(last_bar=BAR, facts=crossing())
        gateway = RecordingGateway()

        result = await evaluate_once(pool, archive, watch, _alerts(gateway))

        assert result.announced is True
        [(destination, text)] = gateway.sent
        assert destination == "operator"
        assert "US100" in text and "long" in text
        async with pool.acquire() as conn:
            written = await store.last_decision(conn, watch.strategy_id, watch.symbol)
            assert written is not None
            assert await conn.fetchval(
                "SELECT notified_at FROM decisions WHERE id = $1", written.id
            )

    async def test_a_refusal_says_nothing(self, pool) -> None:
        watch = await a_watch(pool)
        archive = FakeArchive(last_bar=BAR, facts=flat())
        gateway = RecordingGateway()

        result = await evaluate_once(pool, archive, watch, _alerts(gateway))

        assert result.decision is not None and result.decision.action == "no_trade"
        assert result.announced is False
        assert gateway.sent == []

    async def test_the_same_setup_on_the_next_bar_is_not_announced_again(self, pool) -> None:
        """One entry that stands for ten bars is ten identical decisions; the operator is told once."""
        watch = await a_watch(pool)
        archive = FakeArchive(last_bar=BAR, facts=crossing())
        gateway = RecordingGateway()
        announcing = _alerts(gateway)
        await evaluate_once(pool, archive, watch, announcing)

        archive.last_bar = BAR + timedelta(minutes=15)
        result = await evaluate_once(pool, archive, watch, announcing)

        assert result.recorded is True
        assert result.announced is False
        assert len(gateway.sent) == 1

    @pytest.mark.parametrize(
        "failure",
        [GatewayRefused("the gateway refused: 429"), GatewayUnreachable("no answer")],
        ids=["refused", "unreachable"],
    )
    async def test_a_failed_delivery_leaves_the_decision_recorded_and_unmarked(
        self, pool, failure: Exception
    ) -> None:
        watch = await a_watch(pool)
        archive = FakeArchive(last_bar=BAR, facts=crossing())

        result = await evaluate_once(pool, archive, watch, _alerts(RecordingGateway(failure)))

        assert result.recorded is True
        assert result.announced is False
        async with pool.acquire() as conn:
            written = await store.last_decision(conn, watch.strategy_id, watch.symbol)
            assert written is not None and written.decision.action == "trade"
            assert (
                await conn.fetchval("SELECT notified_at FROM decisions WHERE id = $1", written.id)
            ) is None

    async def test_a_refused_setup_is_tried_again_on_the_next_bar(self, pool) -> None:
        """The whole retry this system has. The first delivery is refused, so no marker is written,
        and the same setup on the next bar is news again rather than a repetition."""
        watch = await a_watch(pool)
        archive = FakeArchive(last_bar=BAR, facts=crossing())
        await evaluate_once(
            pool, archive, watch, _alerts(RecordingGateway(GatewayUnreachable("no answer")))
        )

        archive.last_bar = BAR + timedelta(minutes=15)
        gateway = RecordingGateway()
        result = await evaluate_once(pool, archive, watch, _alerts(gateway))

        assert result.announced is True
        assert len(gateway.sent) == 1
        async with pool.acquire() as conn:
            written = await store.last_decision(conn, watch.strategy_id, watch.symbol)
            assert written is not None and written.notified_at is not None

    async def test_a_gateway_configured_later_announces_the_setup_that_is_standing(
        self, pool
    ) -> None:
        """Clearing the address and restarting is the rollback, so putting it back is the ordinary
        way in. A channel that had nothing to say for the standing setup would stay silent until the
        direction flipped, which can be a day."""
        watch = await a_watch(pool)
        archive = FakeArchive(last_bar=BAR, facts=crossing())
        await evaluate_once(pool, archive, watch, None)

        archive.last_bar = BAR + timedelta(minutes=15)
        gateway = RecordingGateway()
        result = await evaluate_once(pool, archive, watch, _alerts(gateway))

        assert result.announced is True
        [(_, text)] = gateway.sent
        assert "US100" in text and "long" in text

    async def test_no_gateway_leaves_the_decision_and_the_pass_untouched(self, pool) -> None:
        """The rollback lever, and a supported state: the platform decides, and being unable to say
        so is never a reason not to have decided."""
        watch = await a_watch(pool)
        archive = FakeArchive(last_bar=BAR, facts=crossing())

        result = await evaluate_once(pool, archive, watch, None)

        assert result.recorded is True
        assert result.announced is False
        assert result.decision is not None and result.decision.action == "trade"


def test_the_message_names_the_levels_and_gives_no_order() -> None:
    """This platform decides and never touches an account, so the message must not read like one."""
    text = message("baseline_ma_cross", "US100", _trade())

    assert "US100 — long (baseline_ma_cross)" in text
    assert "entry 100.0" in text and "stop 98.0" in text and "target 106.0" in text
    assert "reward/risk 3.00" in text
    for word in ("buy", "sell", "size", "lot"):
        assert word not in text.lower()

"""The backtest, and the two tests that are the whole reason it can be believed.

`test_incremental_and_batch_agree` and `test_a_longer_range_does_not_change_the_common_part`
are not two tests of the same thing. The first catches a slice that carried the future
backwards; the second catches a read whose *answers* change when more history is added.
Either one alone passes over the defect the other exists for.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta

import pytest

from strategy.archive import FactsRead
from strategy.backtest import batch, incremental, measure, resolve, run, slice_at
from strategy.backtest.__main__ import _chosen, named
from strategy.backtest.costs import FREE, CostModel
from strategy.backtest.metrics import attribute
from strategy.backtest.report import NotComparable, Report, compare
from strategy.backtest.simulate import apply_daily_stop
from strategy.catalogue import get
from strategy.config import Settings
from strategy.spec import Candle, Decision, Facts, FactValue, Marker, Zone

SPEC = get("baseline_ma_cross")
PARAMS = SPEC.resolve_params()
START = datetime(2026, 8, 1, tzinfo=UTC)


def stamps(count: int) -> list[datetime]:
    return [START + timedelta(hours=index) for index in range(count)]


class ReplayArchive:
    """An archive holding one generated history, answering any window out of it.

    The point of generating rather than fixing the data: `read_facts` must answer a window
    ending at bar *i* with exactly what the full read says at bar *i*, which is the archive's
    own no-repaint guarantee. Modelling that here is what makes the incremental-versus-batch
    comparison a test of this module rather than of the double.
    """

    def __init__(self, closes: list[float], fast: list[float], slow: list[float], atr: list[float]):
        self.times = stamps(len(closes))
        self.candles = tuple(
            Candle(time=time, open=close, high=close + 1.0, low=close - 1.0, close=close)
            for time, close in zip(self.times, closes, strict=True)
        )
        self.series = {"fast": fast, "slow": slow, "range": atr}
        self.reads = 0

    async def read_facts(self, spec, symbol, params, *, as_of, bars_from=None):
        self.reads += 1
        upto = sum(1 for time in self.times if time <= as_of)
        values = {
            "fast": self._value("fast", "ema", upto),
            "slow": self._value("slow", "ema", upto),
            "range": self._value("range", "atr", upto),
        }
        return FactsRead(
            facts=Facts(
                symbol=symbol,
                as_of=as_of,
                candles=self.candles[:upto],
                values=values,
            ),
            gaps=(),
        )

    def _value(self, key: str, line: str, upto: int) -> FactValue:
        return FactValue(
            key=key,
            resolution="HOUR",
            times=tuple(self.times[:upto]),
            lines={line: tuple(self.series[key][:upto])},
        )


def a_history(bars: int = 60) -> ReplayArchive:
    """A history that crosses several times, so a replay has something to decide."""
    closes, fast, slow, atr = [], [], [], []
    for index in range(bars):
        wave = 10.0 * (1 if (index // 7) % 2 == 0 else -1)
        closes.append(100.0 + index * 0.5 + wave * 0.1)
        fast.append(100.0 + wave)
        slow.append(100.0)
        atr.append(2.0)
    return ReplayArchive(closes, fast, slow, atr)


class TestLookAhead:
    async def test_incremental_and_batch_agree(self) -> None:
        """The one test that catches look-ahead, and it works by comparing this module
        against itself: one driver reads the whole range and slices, the other reads a
        window per bar. A difference is the future having leaked backwards."""
        archive = a_history()
        window = (archive.times[10], archive.times[-1])

        one = await batch(archive, SPEC, "US100", PARAMS, start=window[0], end=window[1])
        other = await incremental(archive, SPEC, "US100", PARAMS, start=window[0], end=window[1])

        assert [(r.as_of, r.decision) for r in one] == [(r.as_of, r.decision) for r in other]
        assert one, "the fixture decided nothing, so this proved nothing"

    async def test_a_longer_range_does_not_change_the_common_part(self) -> None:
        """The other half: a decision must depend only on the data up to its own bar, so
        extending the range forward may add decisions and must never revise one."""
        archive = a_history()
        start = archive.times[10]

        shorter = await batch(archive, SPEC, "US100", PARAMS, start=start, end=archive.times[40])
        longer = await batch(archive, SPEC, "US100", PARAMS, start=start, end=archive.times[-1])

        common = {r.as_of: r.decision for r in longer}
        assert all(common[r.as_of] == r.decision for r in shorter)
        assert len(longer) > len(shorter)

    async def test_the_batch_driver_reads_the_archive_once(self) -> None:
        """What makes a backtest over years finish: one read rather than one per bar."""
        archive = a_history()

        await batch(archive, SPEC, "US100", PARAMS, start=archive.times[10], end=archive.times[-1])

        assert archive.reads == 1


class TestSlicing:
    def test_what_a_zone_later_became_is_masked(self) -> None:
        """The subtle one. The zone existed at this bar; what happened to it afterwards is
        exactly the fact a strategy must not have, and a whole-range read carries it."""
        times = stamps(5)
        zone = Zone(
            start=times[0],
            end=times[4],
            top=110.0,
            bottom=100.0,
            direction="bullish",
            touched_at=times[3],
            filled_at=times[4],
        )
        read = FactsRead(
            facts=Facts(
                symbol="US100",
                as_of=times[4],
                candles=tuple(
                    Candle(time=t, open=100, high=101, low=99, close=100) for t in times
                ),
                values={"z": FactValue(key="z", resolution="HOUR", times=tuple(times), zones=(zone,))},
            )
        )

        sliced = slice_at(read, times[1], candles=10)

        seen = sliced["z"].zones[0]
        assert seen.touched_at is None
        assert seen.filled_at is None
        assert seen.end is None

    def test_a_zone_that_has_not_begun_is_not_there_at_all(self) -> None:
        times = stamps(5)
        zone = Zone(start=times[3], end=None, top=110.0, bottom=100.0)
        read = FactsRead(
            facts=Facts(
                symbol="US100",
                as_of=times[4],
                candles=tuple(
                    Candle(time=t, open=100, high=101, low=99, close=100) for t in times
                ),
                values={"z": FactValue(key="z", resolution="HOUR", times=tuple(times), zones=(zone,))},
            )
        )

        assert slice_at(read, times[1], candles=10)["z"].zones == ()

    def test_markers_and_lines_stop_at_the_bar(self) -> None:
        times = stamps(5)
        read = FactsRead(
            facts=Facts(
                symbol="US100",
                as_of=times[4],
                candles=tuple(
                    Candle(time=t, open=100, high=101, low=99, close=100) for t in times
                ),
                values={
                    "m": FactValue(
                        key="m",
                        resolution="HOUR",
                        times=tuple(times),
                        lines={"ema": (1.0, 2.0, 3.0, 4.0, 5.0)},
                        markers=tuple(Marker(time=t, label="x") for t in times),
                    )
                },
            )
        )

        sliced = slice_at(read, times[2], candles=10)

        assert sliced["m"].line("ema") == (1.0, 2.0, 3.0)
        assert len(sliced["m"].markers) == 3
        assert len(sliced.candles) == 3


class TestResolvingASetup:
    def setup_method(self) -> None:
        self.decision = Decision.trade(
            direction="long", entry=100.0, stop=98.0, target=106.0, features={"a": 1.0}
        )

    def _bars(self, *ohlc: tuple[float, float]) -> list[Candle]:
        return [
            Candle(time=START + timedelta(hours=index + 1), open=100, high=high, low=low, close=high)
            for index, (high, low) in enumerate(ohlc)
        ]

    def test_a_target_reached_is_the_reward_multiple(self) -> None:
        outcome = resolve(
            self.decision, opened_at=START, following=self._bars((106.5, 100.0)), costs=FREE
        )

        assert outcome is not None
        assert outcome.ending == "target"
        assert outcome.r == pytest.approx(3.0)

    def test_a_stop_reached_is_minus_one(self) -> None:
        outcome = resolve(
            self.decision, opened_at=START, following=self._bars((101.0, 97.5)), costs=FREE
        )

        assert outcome is not None
        assert outcome.ending == "stop"
        assert outcome.r == pytest.approx(-1.0)

    def test_a_bar_that_touches_both_is_a_loss(self) -> None:
        """The candle says both prices traded and not in which order. Assuming the kind one
        is how a strategy's worst bars turn into its best."""
        outcome = resolve(
            self.decision, opened_at=START, following=self._bars((107.0, 97.0)), costs=FREE
        )

        assert outcome is not None
        assert outcome.ending == "stop"

    def test_a_setup_that_never_resolves_is_closed_and_counted(self) -> None:
        outcome = resolve(
            self.decision, opened_at=START, following=self._bars((101.0, 99.5)), costs=FREE
        )

        assert outcome is not None
        assert outcome.ending == "timeout"

    def test_a_setup_at_the_very_end_has_not_happened_yet(self) -> None:
        """Not a timeout: it never had a bar to resolve in, and counting it as one would
        put a made-up result into the accounting."""
        assert resolve(self.decision, opened_at=START, following=[], costs=FREE) is None

    def test_costs_come_off_both_sides(self) -> None:
        """A spread of 2 costs 1 entering and 1 leaving; against a risk of 2 that is a
        whole R of the result, which is exactly why a report has to name its costs."""
        costs = CostModel(spread=2.0)

        outcome = resolve(
            self.decision, opened_at=START, following=self._bars((106.5, 100.0)), costs=costs
        )

        assert outcome is not None
        assert outcome.entry == pytest.approx(101.0)
        assert outcome.r < 3.0


class TestMetrics:
    def _outcome(self, r: float, **features):
        return resolve(
            Decision.trade(
                direction="long", entry=100.0, stop=99.0, target=100.0 + r, features=features
            ),
            opened_at=START,
            following=[
                Candle(
                    time=START + timedelta(hours=1),
                    open=100,
                    high=max(100.0 + r, 100.0),
                    low=min(100.0 + r, 100.0),
                    close=100.0 + r,
                )
            ],
            costs=FREE,
        )

    def test_nothing_measured_is_not_an_error(self) -> None:
        assert measure([]).trades == 0

    def test_expectancy_and_streak_read_the_sequence(self) -> None:
        outcomes = [self._outcome(3.0), self._outcome(-1.0), self._outcome(-1.0)]

        metrics = measure([o for o in outcomes if o])

        assert metrics.trades == 3
        assert metrics.expectancy_r == pytest.approx(1 / 3)
        assert metrics.longest_losing_streak == 2
        assert metrics.max_drawdown_r == pytest.approx(-2.0)

    def test_a_run_with_no_loss_has_no_profit_factor(self) -> None:
        """`None` rather than infinity: printing `inf` invites reading it as a very good
        ratio rather than as an absent one."""
        metrics = measure([o for o in [self._outcome(3.0)] if o])

        assert metrics.profit_factor is None


class TestAttribution:
    def test_a_feature_that_tells_the_halves_apart_is_reported_first(self) -> None:
        """The useful question is not whether the bundle worked but which part of it
        carries the edge."""
        outcomes = []
        for index in range(20):
            strong = index >= 10
            outcome = resolve(
                Decision.trade(
                    direction="long",
                    entry=100.0,
                    stop=99.0,
                    target=103.0 if strong else 99.5,
                    features={"separation": 2.0 if strong else 0.1, "noise": index % 2},
                ),
                opened_at=START + timedelta(hours=index),
                following=[
                    Candle(
                        time=START + timedelta(hours=index + 1),
                        open=100,
                        high=103.5 if strong else 100.0,
                        low=100.0 if strong else 98.5,
                        close=100.0,
                    )
                ],
                costs=FREE,
            )
            assert outcome is not None
            outcomes.append(outcome)

        splits = attribute(outcomes)

        assert splits[0].feature == "separation"
        assert splits[0].separation_r > 0

    def test_a_feature_with_too_few_trades_either_side_is_not_reported(self) -> None:
        outcomes = [
            outcome
            for outcome in [
                resolve(
                    Decision.trade(
                        direction="long", entry=100.0, stop=99.0, target=102.0, features={"a": 1.0}
                    ),
                    opened_at=START,
                    following=[Candle(time=START + timedelta(hours=1), open=100, high=103, low=100, close=102)],
                    costs=FREE,
                )
            ]
            if outcome
        ]

        assert attribute(outcomes) == []


class TestTheDailyLossBudget:
    def _loss(self, day: int):
        return resolve(
            Decision.trade(direction="long", entry=100.0, stop=99.0, target=103.0),
            opened_at=datetime(2026, 8, day, 10, tzinfo=UTC),
            following=[
                Candle(time=datetime(2026, 8, day, 11, tzinfo=UTC), open=100, high=100.5, low=98.0, close=99.0)
            ],
            costs=FREE,
        )

    def test_setups_after_the_budget_is_spent_are_dropped(self) -> None:
        losses = [self._loss(1) for _ in range(4)]

        kept = apply_daily_stop([o for o in losses if o], limit_r=2.0)

        assert len(kept) == 2

    def test_the_budget_resets_the_next_day(self) -> None:
        losses = [self._loss(1), self._loss(1), self._loss(1), self._loss(2)]

        kept = apply_daily_stop([o for o in losses if o], limit_r=2.0)

        assert len(kept) == 3

    def test_without_a_limit_nothing_is_dropped(self) -> None:
        losses = [self._loss(1) for _ in range(4)]

        assert len(apply_daily_stop([o for o in losses if o], limit_r=None)) == 4


class TestTheReport:
    async def test_a_run_names_its_costs_its_parameters_and_its_range(self) -> None:
        archive = a_history()

        report = await run(
            archive,
            "baseline_ma_cross",
            "US100",
            start=archive.times[10],
            end=archive.times[-1],
            costs=CostModel(spread=0.5),
        )

        assert report.costs.spread == 0.5
        assert report.params["fast_period"] == 20
        assert report.range_from == archive.times[10]
        assert "spread 0.5" in report.summary()

    async def test_the_refusals_are_counted_by_kind(self) -> None:
        """A run that refused almost everything for want of data looks identical in its
        metrics to one that simply found no setups."""
        archive = a_history()

        report = await run(
            archive, "baseline_ma_cross", "US100", start=archive.times[10], end=archive.times[-1]
        )

        assert sum(report.refusals.values()) > 0
        assert report.bars > 0

    async def test_a_run_over_a_written_rule_names_its_revision(self) -> None:
        """Two runs of one definition from either side of a change are otherwise
        indistinguishable, and differ in exactly what was being measured."""
        archive = a_history()

        report = await run(
            archive,
            get("baseline_ma_cross"),
            "US100",
            start=archive.times[10],
            end=archive.times[-1],
            revision=3,
            revision_id=41,
        )

        assert report.as_dict()["strategy_revision"] == 3
        assert report.named == "baseline_ma_cross@3"
        assert "baseline_ma_cross@3" in report.summary()

    async def test_the_same_run_twice_gives_the_same_report(self) -> None:
        archive = a_history()
        window = {"start": archive.times[10], "end": archive.times[-1]}

        one = await run(archive, "baseline_ma_cross", "US100", **window)
        other = await run(archive, "baseline_ma_cross", "US100", **window)

        assert one.as_dict() == other.as_dict()


class TestNamingARevisionOnTheCommandLine:
    def test_a_bare_name_means_the_newest(self) -> None:
        assert named("my_rule") == ("my_rule", None)

    def test_an_at_sign_names_a_revision(self) -> None:
        assert named("my_rule@3") == ("my_rule", 3)

    def test_something_that_is_not_a_number_after_the_at_sign_is_refused(self) -> None:
        with pytest.raises(argparse.ArgumentTypeError, match="revision number"):
            named("my_rule@latest")

    async def test_naming_only_coded_entries_reaches_no_database(self) -> None:
        """The floor every strategy is measured against has to be recomputable with nothing
        else standing. The settings below point at a host that does not exist, so a run that
        reached for a connection would say so."""
        settings = Settings(
            database_url="postgresql://nowhere.invalid:5432/strategy?sslmode=require",
            database_user="nobody",
            _env_file=None,
        )

        chosen = await _chosen(settings, [("baseline_ma_cross", None)])

        assert [one.spec.id for one in chosen] == ["baseline_ma_cross"]
        assert chosen[0].revision is None


class TestComparing:
    def _report(self, **overrides) -> Report:
        values = {
            "strategy_id": "one",
            "symbol": "US100",
            "resolution": "HOUR",
            "range_from": START,
            "range_to": START + timedelta(days=30),
            "params": {},
            "costs": FREE,
            "metrics": measure([]),
        }
        values.update(overrides)
        return Report(**values)  # type: ignore[arg-type]

    def test_runs_on_the_same_data_and_costs_compare(self) -> None:
        reports = [self._report(), self._report(strategy_id="two")]

        assert compare(reports) == reports

    def test_two_revisions_of_one_definition_compare(self) -> None:
        """The comparison this command exists for, so differing revisions are the one
        difference `compare` may not refuse."""
        reports = [
            self._report(strategy_revision=1),
            self._report(strategy_revision=2),
        ]

        assert compare(reports) == reports

    def test_runs_on_different_ranges_are_refused(self) -> None:
        with pytest.raises(NotComparable, match="two different questions"):
            compare([self._report(), self._report(range_to=START + timedelta(days=60))])

    def test_runs_on_different_costs_are_refused(self) -> None:
        """The most convincing way to be wrong: two numbers side by side that measured
        different worlds."""
        with pytest.raises(NotComparable):
            compare([self._report(), self._report(costs=CostModel(spread=2.0))])

    def test_one_run_is_not_a_comparison(self) -> None:
        with pytest.raises(NotComparable):
            compare([self._report()])

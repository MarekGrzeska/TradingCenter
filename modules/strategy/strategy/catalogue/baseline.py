"""The strategy of reference: two moving averages crossing, with a stop sized by range.

**Deliberately ordinary, and first on purpose.** It does three jobs no clever strategy could
do as well:

* it tests the contract's honesty — a strategy this simple needing a change in the runtime
  would mean the contract is drawn wrong, and better to learn that here than three
  strategies later;
* it takes the whole pipe for a walk before any new indicator exists — decisions, the
  refusals, the trace, the replay and the backtest all work against it using indicators the
  archive has carried for months;
* it leaves a number. "The strategy works" means nothing until it means "it beats this,
  after costs, on the same data" — which is what makes it the entry every later one is
  measured against rather than an embarrassment to delete.

Nothing here is novel and nothing here is meant to be. A crossing of averages is the oldest
published rule in the business, which is precisely what makes it a fair floor.
"""

from __future__ import annotations

from collections.abc import Mapping

from ..spec import Decision, Fact, Facts, Param, StrategySpec

# The three lines this entry reads, and the names the archive answers them under. `ema`'s
# line is keyed `ema` in the archive's catalogue; `atr`'s is keyed `atr`.
FAST = "fast"
SLOW = "slow"
RANGE = "range"


def _evaluate(facts: Facts, params: Mapping[str, float]) -> Decision:
    """Long when the fast average has just crossed above the slow one, and only then.

    Every refusal below says which condition failed, because a strategy that answers "no"
    for three weeks has to be readable rather than guessable. The order is deliberate: the
    cheapest and most common refusal first, so the usual answer is also the shortest path.
    """
    fast = facts.get(FAST)
    slow = facts.get(SLOW)
    atr = facts.get(RANGE)
    if fast is None or slow is None or atr is None:
        return Decision.no_trade("a fact this strategy declared was not read")
    # An error on one fact is the archive saying it cannot compute that one — never that
    # the answer was nothing. Refusing here keeps a missing average from reading as a
    # crossing that did not happen.
    for value in (fast, slow, atr):
        if value.error is not None:
            return Decision.no_trade(f"the archive could not compute {value.key}: {value.error}")

    fast_now, fast_before = fast.last("ema"), fast.previous("ema")
    slow_now, slow_before = slow.last("ema"), slow.previous("ema")
    range_now = atr.last("atr")
    if None in (fast_now, fast_before, slow_now, slow_before, range_now):
        # A line that has not settled yet — the archive read less history than the period
        # needs. Not an error and not a signal: simply not enough to say anything.
        return Decision.no_trade("the averages have not settled over the range read")
    # Narrowed for the type checker; the guard above is what actually establishes it.
    assert fast_now is not None and fast_before is not None
    assert slow_now is not None and slow_before is not None and range_now is not None

    if range_now <= 0:
        return Decision.no_trade("the range is zero, so there is nothing to size a stop by")

    crossed_up = fast_before <= slow_before and fast_now > slow_now
    if not crossed_up:
        return Decision.no_trade(
            "the fast average did not cross above the slow one on this bar",
            features={"separation_atr": (fast_now - slow_now) / range_now},
        )

    close = facts.close
    stop_distance = float(params["stop_atr"]) * range_now
    stop = close - stop_distance
    target = close + float(params["reward_multiple"]) * stop_distance

    # Two features, both meaning something a report can attribute an edge to: how decisive
    # the crossing was, and how far the price sits above the slow average when it happened.
    separation = (fast_now - slow_now) / range_now
    extension = (close - slow_now) / range_now
    return Decision.trade(
        direction="long",
        entry=close,
        stop=stop,
        target=target,
        # Bounded and readable: a crossing is worth most of it, and how decisive it was
        # carries the rest. The weights are this strategy's own, not the platform's.
        score=round(70.0 + 30.0 * min(separation, 1.0), 2),
        features={"separation_atr": separation, "extension_atr": extension},
        reason="the fast average crossed above the slow one",
    )


moving_average_cross = StrategySpec(
    id="baseline_ma_cross",
    name="Baseline · moving-average cross",
    description=(
        "Long when a fast exponential average crosses above a slow one, with the stop a "
        "multiple of average true range below the close and the target a multiple of that "
        "risk. The floor every other strategy has to beat, on indicators the archive "
        "already carries."
    ),
    resolution="HOUR",
    evaluate=_evaluate,
    facts=(
        # `period` points at this strategy's own parameter, so tuning the entry tunes what
        # is read — the declaration stays a declaration and the archive still answers one
        # named indicator per fact.
        Fact(indicator="ema", resolution="HOUR", params={"period": "fast_period"}, key=FAST),
        Fact(indicator="ema", resolution="HOUR", params={"period": "slow_period"}, key=SLOW),
        Fact(indicator="atr", resolution="HOUR", params={"period": "atr_period"}, key=RANGE),
    ),
    params=(
        Param("fast_period", "int", 20, 2, 200),
        Param("slow_period", "int", 50, 3, 400),
        Param("atr_period", "int", 14, 2, 100),
        Param("stop_atr", "float", 2.0, 0.5, 6.0),
        Param("reward_multiple", "float", 3.0, 1.0, 10.0),
    ),
)

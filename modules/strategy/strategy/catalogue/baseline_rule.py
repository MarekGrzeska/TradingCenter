"""`baseline_ma_cross`, written a second time — as data, in the node vocabulary.

**Not a second catalogue entry.** It is deliberately absent from `CATALOGUE`: an operator
reading a list with two identical baselines on it would have to work out which is which,
and neither answer would be useful. This is the measuring stick, kept beside the thing it
measures.

**Why it exists.** Expressing a known, reviewed rule in the node vocabulary and comparing
the two decision by decision is the only honest test of two things at once: whether the
vocabulary is expressive enough to carry a real strategy, and whether the interpreter
computes what it appears to. `tests/test_baseline_rule.py` is that comparison, and a
difference between the twins is a defect in this module, never a nuance.

**One difference is intended, and the test names it.** The coded entry computes
`extension_atr` only on the bar it enters; this one computes both features whenever the
guards have passed, so its refusals carry one feature more. That is the direction "more
information", not a divergence of logic — the interpreter has one place where features are
computed and it is the same place for every rule.

The arithmetic is nested exactly the way the coded entry nests it — `reward_multiple ·
(stop_atr · atr)` and not `(reward_multiple · stop_atr) · atr` — because floating-point
multiplication does not associate, and "identical" here means identical.
"""

from __future__ import annotations

from ..rule import (
    Arith,
    BarRead,
    Call,
    Compare,
    Const,
    Crossed,
    FactRead,
    Guard,
    Logic,
    ParamRef,
    RuleDefinition,
    RuleFact,
    RuleParam,
    Settled,
    Setup,
)
from .baseline import FAST, RANGE, SLOW


def _fast(offset: int = 0) -> FactRead:
    return FactRead(key=FAST, line="ema", offset=offset)


def _slow(offset: int = 0) -> FactRead:
    return FactRead(key=SLOW, line="ema", offset=offset)


def _atr() -> FactRead:
    return FactRead(key=RANGE, line="atr")


def _over_range(numerator: Arith) -> Arith:
    return Arith(op="/", operands=[numerator, _atr()])


# (fast − slow) / atr — how decisive the crossing was.
_SEPARATION = _over_range(Arith(op="-", operands=[_fast(), _slow()]))

# (close − slow) / atr — how far price sits above the slow average.
_EXTENSION = _over_range(Arith(op="-", operands=[BarRead(field="close"), _slow()]))

# stop_atr · atr, the distance both levels are built from.
_STOP_DISTANCE = Arith(op="*", operands=[ParamRef(name="stop_atr"), _atr()])

BASELINE_RULE = RuleDefinition(
    resolution="HOUR",
    candles=300,
    unsettled_reason="the averages have not settled over the range read",
    no_setup_reason="the fast average did not cross above the slow one on this bar",
    facts=[
        RuleFact(key=FAST, indicator="ema", resolution="HOUR", params={"period": "fast_period"}),
        RuleFact(key=SLOW, indicator="ema", resolution="HOUR", params={"period": "slow_period"}),
        RuleFact(key=RANGE, indicator="atr", resolution="HOUR", params={"period": "atr_period"}),
    ],
    params=[
        RuleParam(name="fast_period", type="int", default=20, min=2, max=200),
        RuleParam(name="slow_period", type="int", default=50, min=3, max=400),
        RuleParam(name="atr_period", type="int", default=14, min=2, max=100),
        RuleParam(name="stop_atr", type="float", default=2.0, min=0.5, max=6.0),
        RuleParam(name="reward_multiple", type="float", default=3.0, min=1.0, max=10.0),
    ],
    guards=[
        # First, and this is the ordering the coded entry has too: everything below reads a
        # settled series, and a crossing computed off one that has not filled yet is the
        # defect this whole vocabulary is arranged to make unavailable.
        Guard(
            when=Logic(
                op="not",
                operands=[Settled(of=[_fast(), _fast(1), _slow(), _slow(1), _atr()])],
            ),
            reason="the averages have not settled over the range read",
        ),
        Guard(
            when=Compare(op="<=", left=_atr(), right=Const(value=0.0)),
            reason="the range is zero, so there is nothing to size a stop by",
        ),
    ],
    setups=[
        Setup(
            when=Crossed(direction="above", left=_fast(), right=_slow()),
            direction="long",
            entry=BarRead(field="close"),
            stop=Arith(op="-", operands=[BarRead(field="close"), _STOP_DISTANCE]),
            target=Arith(
                op="+",
                operands=[
                    BarRead(field="close"),
                    Arith(
                        op="*",
                        operands=[
                            ParamRef(name="reward_multiple"),
                            _STOP_DISTANCE,
                        ],
                    ),
                ],
            ),
            score=Call(
                fn="round",
                operands=[
                    Arith(
                        op="+",
                        operands=[
                            Const(value=70.0),
                            Arith(
                                op="*",
                                operands=[
                                    Const(value=30.0),
                                    Call(fn="min", operands=[_SEPARATION, Const(value=1.0)]),
                                ],
                            ),
                        ],
                    ),
                    Const(value=2.0),
                ],
            ),
            reason="the fast average crossed above the slow one",
        )
    ],
    features={"separation_atr": _SEPARATION, "extension_atr": _EXTENSION},
)

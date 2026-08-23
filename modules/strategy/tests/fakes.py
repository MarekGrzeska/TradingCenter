"""Doubles for the one thing this module reaches outward to.

The archive is an HTTP contract, so most tests double it at the transport with `respx` —
that is what `test_archive.py` does, and it is the only honest way to test the client
itself. Above the client, where what matters is what the loop does with an answer rather
than how the answer was parsed, this fake stands in its place.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from strategy.archive import AnnouncedIndicator, AnnouncedParam, FactsRead, Gap
from strategy.spec import Facts, StrategySpec

# The two indicators the strategy of reference reads, spelled the way the real client
# hands them over — every bound a float, because `Archive._announced` coerces them.
DEFAULT_CATALOGUE = {
    "ema": AnnouncedIndicator(
        id="ema",
        name="Exponential moving average",
        group="averages",
        output="lines",
        params=(AnnouncedParam(name="period", type="int", default=20.0, min=2.0, max=5000.0),),
        lines=("ema",),
    ),
    "atr": AnnouncedIndicator(
        id="atr",
        name="Average true range",
        group="volatility",
        output="lines",
        params=(AnnouncedParam(name="period", type="int", default=14.0, min=2.0, max=5000.0),),
        lines=("atr",),
    ),
}


class FakeArchive:
    """An archive that answers whatever the test put in it, and remembers what it was asked.

    `raises` covers the case the loop cares about most: a read that fails is not an empty
    read, and the decision recorded has to say so.
    """

    def __init__(
        self,
        *,
        last_bar: datetime | None = None,
        facts: Facts | None = None,
        gaps: tuple[Gap, ...] = (),
        raises: Exception | None = None,
        facts_raises: Exception | None = None,
        indicators: frozenset[str] = frozenset({"ema", "atr"}),
        catalogue: dict | None = None,
        catalogue_raises: Exception | None = None,
    ) -> None:
        self.last_bar = last_bar
        self.facts = facts
        self.gaps = gaps
        # `raises` fails everything; `facts_raises` fails only the read of the facts, which
        # is the more interesting half — the bar can be had, so there is something to
        # record the refusal against.
        self.raises = raises
        self.facts_raises = facts_raises
        self.indicators = indicators
        # What `announced_catalogue` answers. Defaulted to the two the strategy of
        # reference reads, so a test about something else does not have to state them.
        self.catalogue = DEFAULT_CATALOGUE if catalogue is None else catalogue
        self.catalogue_raises = catalogue_raises
        self.reads: list[tuple] = []

    async def announced_indicators(self) -> frozenset[str]:
        return self.indicators

    async def announced_catalogue(self) -> dict:
        if self.catalogue_raises is not None:
            raise self.catalogue_raises
        return self.catalogue

    async def last_closed_bar(self, symbol: str, resolution: str) -> datetime | None:
        self.reads.append(("last_closed_bar", symbol, resolution))
        if self.raises is not None:
            raise self.raises
        return self.last_bar

    async def read_facts(
        self,
        spec: StrategySpec,
        symbol: str,
        params: Mapping[str, float],
        *,
        as_of: datetime,
    ) -> FactsRead:
        self.reads.append(("read_facts", symbol, spec.id, as_of))
        if self.facts_raises is not None:
            raise self.facts_raises
        if self.raises is not None:
            raise self.raises
        assert self.facts is not None, "the test did not set the facts to answer with"
        return FactsRead(facts=self.facts, gaps=self.gaps)

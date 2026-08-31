"""What the archive holds, as this module's own shapes — deliberately not the provider's, which sends
three fields as JSON inside a string, positionally aligned."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum


class Surface(str, Enum):
    """Which of the provider's two surfaces a value came from. Recorded on every sample because the
    sampler's saving rests on a measured equivalence, and a measured fact has to stay checkable."""

    GAMMA = "gamma"
    CLOB = "clob"


@dataclass(frozen=True, slots=True)
class Outcome:
    """One thing that can happen, and the only level at which there is a price. `position` is the
    provider's ordering, which pairs an outcome with its token; `token_id` is what the book is queried by."""

    position: int
    name: str
    token_id: str
    id: int | None = None
    oldest_available_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Market:
    """One question with a definite answer; two outcomes is the common case, not the rule.
    `resolved_outcome` stops the sampling, and `neg_risk` says the Yes prices need not sum to one."""

    provider_market_id: str
    question: str
    outcomes: tuple[Outcome, ...]
    id: int | None = None
    condition_id: str | None = None
    group_item_title: str | None = None
    neg_risk: bool = False
    closed: bool = False
    resolved_outcome: str | None = None

    @property
    def resolved(self) -> bool:
        return self.resolved_outcome is not None


@dataclass(frozen=True, slots=True)
class Event:
    """What is tracked, and the unit one provider request covers however many markets it
    holds — which is what makes the ceiling affordable in events rather than in markets."""

    provider_event_id: str
    slug: str
    title: str
    markets: tuple[Market, ...] = ()
    id: int | None = None
    group_id: int | None = None
    group_name: str | None = None
    tracked_at: datetime | None = None
    refreshed_at: datetime | None = None

    @property
    def resolved(self) -> bool:
        """Every market answered. The event stays on the list, marked — it does not vanish
        by itself, because its history is the point."""
        return bool(self.markets) and all(market.resolved for market in self.markets)


@dataclass(frozen=True, slots=True)
class Sample:
    """One outcome's price at one moment, however it arrived. Two valuations, at least one present.
    `quoted_at` is what the valuation is *about* — without it a nine-hour-old trade reads as fresh."""

    outcome_id: int
    observed_at: datetime
    source: Surface
    midpoint: Decimal | None = None
    last_trade: Decimal | None = None
    quoted_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.midpoint is None and self.last_trade is None:
            raise ValueError(
                "a sample with neither a midpoint nor a last trade is not a price; a "
                "failed read must write nothing rather than a placeholder"
            )


@dataclass(frozen=True, slots=True)
class CollectedRange:
    """A window this module has actually read from the provider. No sample because nobody traded and no
    sample because the module was not running are the same absence in the samples table."""

    starts_at: datetime
    ends_at: datetime


@dataclass(frozen=True, slots=True)
class Group:
    """A local category. Not the provider's tag — that describes the public database and is
    what browsing filters on; this describes what we watch."""

    name: str
    id: int | None = None
    event_ids: tuple[int, ...] = field(default_factory=tuple)

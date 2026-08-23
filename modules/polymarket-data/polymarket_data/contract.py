"""What this module answers with. These models are the published shape.

Separate from the internal ones on purpose, and here that separation is load-bearing twice
over. It keeps the provider's shapes out of the terminal — Polymarket sends three fields as
JSON inside a string, and a field it renames must be a change in this module and nowhere else.
And it keeps `Decimal` off the wire, where JSON has no such thing.

Prices are **probabilities on 0..1**, never percentages, and every field that carries one says
so in its description. A consumer that reads 0,62 as 62 is wrong by two orders of magnitude
without a single error on the way.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from .models import Event, Market, Outcome, Sample

PROBABILITY = "the market's probability for this outcome, 0..1 — not a percentage"


def _f(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


class Problem(BaseModel):
    """One refusal shape for every route, so a consumer handles one thing.

    `retryable` is the field that matters: a consumer has to be able to tell "ask again" from
    "fix the request" from "tell the operator", and over HTTP a refusal and an empty answer
    look alike.
    """

    detail: str
    cause: Literal["module", "provider", "request"] = "module"
    retryable: bool = False


class OutcomeOut(BaseModel):
    id: int
    name: str = Field(description="the outcome's own name, e.g. 'Yes' or a candidate's")
    position: int = Field(description="the provider's ordering, which pairs it with its token")
    price: float | None = Field(default=None, description=PROBABILITY)
    price_at: datetime | None = Field(
        default=None, description="when that price was observed, UTC — a price without it is a "
        "number nobody can date"
    )
    last_trade: float | None = Field(
        default=None, description="the last traded price where the provider gives one, 0..1"
    )
    collected_from: datetime | None = Field(
        default=None, description="how far back this outcome's collected history reaches, UTC"
    )

    @classmethod
    def of(cls, outcome: Outcome, sample: Sample | None) -> OutcomeOut:
        return cls(
            id=outcome.id or 0,
            name=outcome.name,
            position=outcome.position,
            price=_f(sample.midpoint) if sample else None,
            price_at=sample.observed_at if sample else None,
            last_trade=_f(sample.last_trade) if sample else None,
            collected_from=outcome.oldest_available_at,
        )


class MarketOut(BaseModel):
    id: int
    question: str
    label: str | None = Field(
        default=None,
        description="what this market is called inside its event — a candidate's name in a "
        "'who wins' event, where the question is the same for all of them",
    )
    neg_risk: bool = Field(
        default=False,
        description="this market is one of a mutually-exclusive set; the Yes prices across "
        "that set need not sum to 1 and must not be presented as if they did",
    )
    resolved_outcome: str | None = Field(
        default=None, description="which outcome won, once the provider has answered"
    )
    outcomes: list[OutcomeOut]

    @classmethod
    def of(cls, market: Market, samples: dict[int, Sample]) -> MarketOut:
        return cls(
            id=market.id or 0,
            question=market.question,
            label=market.group_item_title,
            neg_risk=market.neg_risk,
            resolved_outcome=market.resolved_outcome,
            outcomes=[
                OutcomeOut.of(outcome, samples.get(outcome.id or 0))
                for outcome in market.outcomes
            ],
        )


class CollectionOut(BaseModel):
    """Whether prices are actually arriving. Being on the list does not prove they are."""

    # Three, and there is no fourth to add back: an observation is collected or it is gone,
    # so a state meaning "on the list and not collecting" has no producer any more
    # (`openspec/specs/polymarket-data-tracking`).
    state: Literal["collecting", "stalled", "resolved"]
    last_sample_at: datetime | None = None
    reason: str | None = Field(
        default=None, description="why collection is not running, when it is not"
    )


class TrackedEventOut(BaseModel):
    id: int
    provider_event_id: str
    slug: str
    title: str
    url: str = Field(description="the event on polymarket.com, for an operator to open")
    group: str | None = None
    tracked_at: datetime | None = None
    collection: CollectionOut
    markets: list[MarketOut]

    @classmethod
    def of(
        cls, event: Event, samples: dict[int, Sample], collection: CollectionOut
    ) -> TrackedEventOut:
        return cls(
            id=event.id or 0,
            provider_event_id=event.provider_event_id,
            slug=event.slug,
            title=event.title,
            url=f"https://polymarket.com/event/{event.slug}",
            group=event.group_name,
            tracked_at=event.tracked_at,
            collection=collection,
            markets=[MarketOut.of(market, samples) for market in event.markets],
        )


class TrackRequest(BaseModel):
    reference: str = Field(
        description="the event's address on polymarket.com, or its slug — the operator "
        "copies one, a model has the other, and both name the same observation"
    )
    group: str | None = Field(
        default=None, description="the observation group to file it under; created if new"
    )


class TrackResult(BaseModel):
    event: TrackedEventOut
    already_tracked: bool = Field(
        description="true when this event was already under observation; no second "
        "observation was created and no history was disturbed"
    )


class GroupOut(BaseModel):
    id: int
    name: str
    event_count: int


class PricePoint(BaseModel):
    at: datetime
    price: float | None = Field(default=None, description=PROBABILITY)
    last_trade: float | None = None


class HistoryOut(BaseModel):
    outcome_id: int
    points: list[PricePoint]
    collected_from: datetime | None = Field(
        default=None,
        description="the earliest moment this outcome's history has actually been "
        "collected for — a request reaching before it is answered with what exists, and "
        "the absence before it is not a market that was silent",
    )
    collected_to: datetime | None = None


class WindowChange(BaseModel):
    window: Literal["5m", "1h", "4h", "24h", "7d"]
    change: float | None = Field(
        default=None,
        description="the change in probability over the window, in points of the 0..1 "
        "scale; null when the collected history does not reach back that far",
    )
    unavailable: str | None = Field(
        default=None,
        description="why there is no value — never reported as a change of zero, which "
        "would be a claim about the market rather than about the archive",
    )
    baseline_at: datetime | None = Field(
        default=None,
        description="the moment the base point actually came from. The provider's spacing "
        "wobbles and widens on its own, so this is rarely exactly the window's edge",
    )


class OutcomeChanges(BaseModel):
    outcome_id: int
    name: str
    price: float | None = Field(default=None, description=PROBABILITY)
    windows: list[WindowChange]


class ChangesOut(BaseModel):
    event_id: int
    outcomes: list[OutcomeChanges]


class SnapshotEntry(BaseModel):
    event_id: int
    event_slug: str
    market_id: int
    market_label: str | None
    outcome_id: int
    outcome_name: str
    price: float | None = Field(default=None, description=PROBABILITY)
    price_at: datetime | None = None


class SnapshotOut(BaseModel):
    """The whole screen in one read.

    A request per event would be a request per row, and one measured event holds 128 markets.
    """

    entries: list[SnapshotEntry]


class DeletionResult(BaseModel):
    samples_deleted: int
    ranges_deleted: int

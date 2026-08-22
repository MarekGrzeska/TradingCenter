"""Builders for the shapes the tests need, so setup stays out of the assertions."""

from __future__ import annotations

from itertools import count

from polymarket_data.models import Event, Market, Outcome

_tokens = count(1)


def outcome(name: str, position: int = 0, token_id: str | None = None) -> Outcome:
    return Outcome(
        position=position,
        name=name,
        token_id=token_id or f"token-{next(_tokens)}",
    )


def binary_market(question: str, provider_market_id: str | None = None, **kwargs) -> Market:
    """Two outcomes — the common case, and deliberately not the only one the model allows."""
    return Market(
        provider_market_id=provider_market_id or f"market-{next(_tokens)}",
        question=question,
        outcomes=(outcome("Yes", 0), outcome("No", 1)),
        **kwargs,
    )


def multi_outcome_market(
    question: str, names: tuple[str, ...], provider_market_id: str | None = None, **kwargs
) -> Market:
    return Market(
        provider_market_id=provider_market_id or f"market-{next(_tokens)}",
        question=question,
        outcomes=tuple(outcome(name, index) for index, name in enumerate(names)),
        **kwargs,
    )


def event(
    slug: str = "an-event",
    *,
    markets: tuple[Market, ...] | None = None,
    provider_event_id: str | None = None,
    title: str | None = None,
) -> Event:
    return Event(
        provider_event_id=provider_event_id or f"event-{next(_tokens)}",
        slug=slug,
        title=title or slug.replace("-", " ").title(),
        markets=markets if markets is not None else (binary_market("Will it?"),),
    )

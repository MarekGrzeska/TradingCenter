"""The provider's shapes turned into this module's, in one place with no network in it.

Everything here is pure, so the awkward parts of Polymarket's payloads are testable without
reaching for it. There are three awkward parts and they are all in one sentence: `outcomes`,
`outcomePrices` and `clobTokenIds` arrive as **JSON inside a string**, positionally aligned
with one another, and nothing in the payload says they are.
"""

from __future__ import annotations

import json
import logging
import re
from decimal import Decimal, InvalidOperation

from .models import Event, Market, Outcome

log = logging.getLogger(__name__)

# `https://polymarket.com/event/<slug>` — with or without a market fragment after it, which
# an operator's copied address usually has.
_EVENT_URL = re.compile(r"polymarket\.com/(?:event|market)/([A-Za-z0-9_-]+)")


class ProviderPayloadUnusable(ValueError):
    """The provider answered with something that is not an event.

    Distinct from "the provider refused" and from "the provider has no such event": this is
    a shape that changed, and it must not read as either of the other two.
    """


def slug_from(reference: str) -> str:
    """The event slug out of whatever the caller had at hand.

    An operator copies an address out of the browser; a model has the slug from a search.
    Both name the same observation, so both arrive here rather than at two code paths that
    can disagree.
    """
    stripped = reference.strip()
    match = _EVENT_URL.search(stripped)
    if match:
        return match.group(1)
    if "/" in stripped or " " in stripped:
        raise ProviderPayloadUnusable(
            f"{reference!r} is neither a Polymarket event address nor a slug"
        )
    return stripped


def _json_list(raw: object, field: str) -> list:
    """One of the three fields the provider sends as JSON inside a string.

    Tolerant of it one day being an actual list, because that is the change that would
    otherwise break every event on the day it lands, silently, by parsing nothing.
    """
    if isinstance(raw, list):
        return raw
    if raw in (None, ""):
        return []
    if not isinstance(raw, str):
        raise ProviderPayloadUnusable(f"{field} is neither a list nor a JSON string: {raw!r}")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as err:
        raise ProviderPayloadUnusable(f"{field} is not parseable JSON: {raw!r}") from err
    if not isinstance(parsed, list):
        raise ProviderPayloadUnusable(f"{field} did not parse to a list: {raw!r}")
    return parsed


def _price(raw: object) -> Decimal | None:
    if raw in (None, ""):
        return None
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None
    # The provider's prices are probabilities. Anything outside the interval is not a price
    # this archive can store, and the database says so too.
    return value if Decimal(0) <= value <= Decimal(1) else None


def _resolved_outcome(closed: bool, names: list[str], prices: list[Decimal | None]) -> str | None:
    """Which outcome won, when the provider has answered.

    Read off the prices rather than from a field, because there is no field: a resolved
    market prices the winner at exactly 1 and everything else at 0. Inferred only when the
    market is closed *and* the shape is unambiguous — one outcome at 1 — so a market
    trading at 0,999 an hour before it resolves is not recorded as decided.
    """
    if not closed:
        return None
    winners = [name for name, price in zip(names, prices, strict=False) if price == Decimal(1)]
    return winners[0] if len(winners) == 1 else None


def market_from(payload: dict) -> Market:
    names = [str(name) for name in _json_list(payload.get("outcomes"), "outcomes")]
    tokens = [str(token) for token in _json_list(payload.get("clobTokenIds"), "clobTokenIds")]
    prices = [_price(value) for value in _json_list(payload.get("outcomePrices"), "outcomePrices")]

    if not names or not tokens:
        raise ProviderPayloadUnusable(
            f"market {payload.get('id')!r} carries no outcomes or no tokens"
        )
    if len(names) != len(tokens):
        # Positional alignment is the only thing pairing an outcome with the token its price
        # is asked for by. Lengths that disagree mean the pairing is a guess, and a guess
        # here writes one outcome's price under another outcome's name.
        raise ProviderPayloadUnusable(
            f"market {payload.get('id')!r} has {len(names)} outcomes and {len(tokens)} "
            "tokens; the two are paired by position and cannot be paired at different lengths"
        )

    closed = bool(payload.get("closed"))
    return Market(
        provider_market_id=str(payload["id"]),
        condition_id=payload.get("conditionId"),
        question=str(payload.get("question") or ""),
        group_item_title=payload.get("groupItemTitle") or None,
        neg_risk=bool(payload.get("negRisk")),
        closed=closed,
        resolved_outcome=_resolved_outcome(closed, names, prices),
        outcomes=tuple(
            Outcome(position=index, name=name, token_id=token)
            for index, (name, token) in enumerate(zip(names, tokens, strict=True))
        ),
    )


def event_from(payload: dict) -> Event:
    """The whole event. A market that will not parse is dropped with a line in the log
    rather than taking the event down with it — one malformed market out of a hundred and
    twenty-eight should not cost the other hundred and twenty-seven."""
    if not isinstance(payload, dict) or "id" not in payload:
        raise ProviderPayloadUnusable("the provider's answer is not an event")

    markets: list[Market] = []
    for raw in payload.get("markets") or []:
        try:
            markets.append(market_from(raw))
        except ProviderPayloadUnusable:
            log.warning(
                "event %s: market %s could not be read and was skipped",
                payload.get("slug"),
                raw.get("id") if isinstance(raw, dict) else "?",
            )

    if not markets:
        raise ProviderPayloadUnusable(
            f"event {payload.get('slug')!r} has no market this module can read"
        )

    return Event(
        provider_event_id=str(payload["id"]),
        slug=str(payload.get("slug") or payload["id"]),
        title=str(payload.get("title") or payload.get("slug") or payload["id"]),
        markets=tuple(markets),
    )


def prices_from(payload: dict) -> dict[str, tuple[Decimal | None, Decimal | None]]:
    """`{token_id: (midpoint, last_trade)}` for every outcome of every market of the event.

    This is the measurement the sampler rests on. `outcomePrices` is the order book's
    midpoint, to the digit, for every outcome at once — checked 22 August 2026 across three
    markets and six outcomes. One request per event therefore prices the whole event, where
    the source application spent two requests per market.

    `lastTradePrice` sits on the market rather than on the outcome and describes its first
    outcome — the "Yes" side — so it is attached there and nowhere else. Inventing the
    complement for the other side would be a number that looks like data.
    """
    prices: dict[str, tuple[Decimal | None, Decimal | None]] = {}
    for raw in payload.get("markets") or []:
        if not isinstance(raw, dict):
            continue
        try:
            tokens = [str(token) for token in _json_list(raw.get("clobTokenIds"), "clobTokenIds")]
            midpoints = [
                _price(value) for value in _json_list(raw.get("outcomePrices"), "outcomePrices")
            ]
        except ProviderPayloadUnusable:
            continue
        last_trade = _price(raw.get("lastTradePrice"))
        for index, token in enumerate(tokens):
            midpoint = midpoints[index] if index < len(midpoints) else None
            if midpoint is None and (index != 0 or last_trade is None):
                continue
            prices[token] = (midpoint, last_trade if index == 0 else None)
    return prices


def history_points(payload: dict) -> list[tuple[int, Decimal]]:
    """`[(unix_seconds, price)]` from the order book's time series, oldest first.

    The spacing is not uniform and is not promised to be: measured at 57, 59, 60, 61 and 63
    seconds inside one series, and widening on its own for a longer range. Anything reading
    this must treat the interval as an observation, never as a grid.
    """
    points: list[tuple[int, Decimal]] = []
    for entry in payload.get("history") or []:
        if not isinstance(entry, dict):
            continue
        moment = entry.get("t")
        price = _price(entry.get("p"))
        if isinstance(moment, int | float) and price is not None:
            points.append((int(moment), price))
    points.sort(key=lambda point: point[0])
    return points

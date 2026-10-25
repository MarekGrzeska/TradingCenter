"""A cost profile read off the broker, through the candle archive (design D1): the spread from the current bid and ask,
the financing and the settlement hour from the instrument's terms. Nothing missing is filled in — a value the broker did
not give is a refusal that names it, because a default here would be a cost nobody chose."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .archive import Archive
from .costs import CostModel

# The model charges once a day at one hour; a provider charging on another rhythm is a model this one is not.
DAILY_MINUTES = 1440


class BrokerCostsMissing(Exception):
    """The broker's answer lacks a value the profile needs; the message names it."""


@dataclass(frozen=True)
class BrokerCosts:
    costs: CostModel
    # The provider's own numbers the costs were converted from, kept beside them so a misreading can be seen.
    raw: dict[str, Any]


def from_broker(symbol: str, hits: list[Any], terms: dict[str, Any]) -> BrokerCosts:
    quote = next((h for h in hits if isinstance(h, dict) and h.get("symbol") == symbol), None)
    if quote is None:
        raise BrokerCostsMissing(f"the broker's search does not list {symbol} itself, so it has no price for it")
    bid, ask = _number(quote, "bid", symbol), _number(quote, "ask", symbol)
    if ask < bid:
        raise BrokerCostsMissing(f"the broker quotes {symbol} with an ask ({ask:g}) below its bid ({bid:g})")
    long_rate = _number(terms, "overnight_long_rate", symbol)
    short_rate = _number(terms, "overnight_short_rate", symbol)
    unit = terms.get("overnight_rate_unit")
    if unit != "PERCENTAGE":
        raise BrokerCostsMissing(f"the broker states {symbol}'s overnight rates in {unit!r}, not as a percentage")
    interval = terms.get("overnight_charge_interval_minutes")
    if interval != DAILY_MINUTES:
        raise BrokerCostsMissing(
            f"the broker charges {symbol}'s financing every {interval!r} minutes; the cost model knows a daily charge only"
        )
    charge_at = terms.get("overnight_charge_at")
    if not isinstance(charge_at, str):
        raise BrokerCostsMissing(f"the broker gives no overnight_charge_at for {symbol}")
    try:
        rollover = datetime.fromisoformat(charge_at)
    except ValueError:
        raise BrokerCostsMissing(f"the broker's overnight_charge_at for {symbol} is not a moment: {charge_at!r}") from None
    if rollover.utcoffset() is None:
        raise BrokerCostsMissing(f"the broker's overnight_charge_at for {symbol} names no zone: {charge_at!r}")
    costs = CostModel(
        # Rounded: 3996.02 - 3995.27 is 0.7500000000002 in floating point, and the profile is read by a person.
        spread=round(ask - bid, 10),
        slippage=0.0,
        # capital.com: a percentage of the position's value per day, negative when the holder pays (verified against the
        # demo account's charges, design D3). Here positive is a charge, and a fraction.
        overnight_long=-long_rate / 100,
        overnight_short=-short_rate / 100,
        rollover_hour=rollover.astimezone(UTC).hour,
    )
    raw = {
        "bid": bid, "ask": ask, "tradeable": quote.get("tradeable"),
        "overnight_long_rate": long_rate, "overnight_short_rate": short_rate, "overnight_rate_unit": unit,
        "overnight_charge_at": charge_at, "overnight_charge_interval_minutes": interval,
    }
    return BrokerCosts(costs, raw)


@dataclass(frozen=True)
class BrokerMargin:
    # A fraction of the position's value; capital.com states it as a percentage.
    margin_factor: float
    raw: dict[str, Any]


def margin_from_terms(symbol: str, terms: dict[str, Any]) -> BrokerMargin:
    value = _number(terms, "margin_factor", symbol)
    unit = terms.get("margin_factor_unit")
    if unit != "PERCENTAGE":
        raise BrokerCostsMissing(f"the broker states {symbol}'s deposit in {unit!r}, not as a percentage")
    if not 0 < value <= 100:
        raise BrokerCostsMissing(f"the broker's deposit for {symbol} is {value:g}%, which is no deposit")
    return BrokerMargin(round(value / 100, 10), {"margin_factor": value, "margin_factor_unit": unit})


async def fetch_margin(archive: Archive, symbol: str) -> BrokerMargin:
    return margin_from_terms(symbol, await archive.terms(symbol))


async def fetch(archive: Archive, symbol: str) -> BrokerCosts:
    """Both reads at once; `ArchiveUnavailable` when either went unanswered, `BrokerCostsMissing` when one lacks a value."""
    hits, terms = await asyncio.gather(archive.search(symbol), archive.terms(symbol))
    return from_broker(symbol, hits, terms)


def _number(source: dict[str, Any], name: str, symbol: str) -> float:
    value = source.get(name)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise BrokerCostsMissing(f"the broker gives no {name} for {symbol}")
    return float(value)

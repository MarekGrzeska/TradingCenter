"""Pure functions: a raw capital.com dict in, a neutral DTO out. No I/O.

Kept free of side effects so the place where the provider's semantics are easiest to
misread can be tested against recorded payloads alone, with no socket and no mock.
"""

from __future__ import annotations

from .dtos import (
    Account,
    AssetClass,
    Candle,
    Direction,
    Instrument,
    Order,
    OrderStatus,
    OrderType,
    Position,
    Resolution,
    WorkingOrder,
)

_ASSET_CLASS = {
    "SHARES": AssetClass.SHARES,
    "INDICES": AssetClass.INDICES,
    "CRYPTOCURRENCIES": AssetClass.CRYPTO,
    "CURRENCIES": AssetClass.CURRENCIES,
    "COMMODITIES": AssetClass.COMMODITIES,
}


def asset_class(instrument_type: str | None) -> AssetClass:
    return _ASSET_CLASS.get(instrument_type or "", AssetClass.OTHER)


def instrument_from_market(m: dict) -> Instrument:
    """From a flat market dict — search results and marketnavigation leaves share it."""
    return Instrument(
        symbol=m["epic"],
        name=m.get("instrumentName", ""),
        asset_class=asset_class(m.get("instrumentType")),
        tradeable=m.get("marketStatus") == "TRADEABLE",
        bid=m.get("bid"),
        ask=m.get("offer"),
        lot_size=m.get("lotSize"),
    )


def _bid(price: dict | None) -> float | None:
    """The bid side of one candle edge.

    Not the midpoint. REST gives both sides per edge, the stream's `classic` OHLC gives
    one, and that one is the bid — so a midpoint here would put a half-spread step at
    every seam between stored history and live candles. On US100 that spread is about
    1.8 points, which is visible on a chart and invisible in a test that only checks
    one source at a time.
    """
    if not price:
        return None
    bid = price.get("bid")
    # Falls back to ask only when the provider omitted bid entirely, which beats a null
    # candle edge; a one-sided quote is rare and still better than no price.
    return bid if bid is not None else price.get("ask")


def _candle_ts(p: dict) -> str:
    """capital.com sends `snapshotTimeUTC` without a zone marker, so a consumer parsing
    it gets local time on most platforms. The `Z` is added here rather than left for
    every caller to remember."""
    utc = p.get("snapshotTimeUTC")
    if utc:
        return utc if utc.endswith("Z") else f"{utc}Z"
    # No UTC field: `snapshotTime` is the broker's local time, so it is passed through
    # unmarked rather than stamped with a `Z` it has not earned.
    return p.get("snapshotTime", "")


def candle_from_price(p: dict, resolution: Resolution) -> Candle:
    return Candle(
        ts=_candle_ts(p),
        open=_bid(p.get("openPrice")),
        high=_bid(p.get("highPrice")),
        low=_bid(p.get("lowPrice")),
        close=_bid(p.get("closePrice")),
        volume=p.get("lastTradedVolume"),
        resolution=resolution,
    )


def account_from_raw(a: dict, active: bool = False) -> Account:
    bal = a.get("balance") or {}
    return Account(
        id=a["accountId"],
        name=a.get("accountName", ""),
        currency=a.get("currency", ""),
        balance=bal.get("balance", 0.0),
        available=bal.get("available", 0.0),
        pnl=bal.get("profitLoss", 0.0),
        active=active,
    )


def position_from_raw(row: dict) -> Position:
    """From a positions[] row: ``{position: {...}, market: {...}}``."""
    p = row.get("position") or {}
    m = row.get("market") or {}
    return Position(
        id=p["dealId"],
        symbol=m.get("epic", ""),
        direction=Direction(p["direction"]),
        size=p.get("size", 0.0),
        open_level=p.get("level"),
        pnl=p.get("upl"),
        currency=p.get("currency"),
    )


def order_from_confirm(c: dict, accepted_status: OrderStatus = OrderStatus.FILLED) -> Order:
    """From a ``GET /confirms/{ref}`` payload.

    ``accepted_status`` is what an ACCEPTED deal means for the action that produced it:
    FILLED for a market order, WORKING for a resting one, CLOSED for a position close,
    CANCELLED for a working-order cancel, UPDATED for an amendment. Anything other than
    ACCEPTED is REJECTED — the provider states one status and the caller needs to know
    which of those five it settled into.
    """
    status = accepted_status if c.get("dealStatus") == "ACCEPTED" else OrderStatus.REJECTED
    deal_id = c.get("dealId")
    affected = c.get("affectedDeals") or []
    if affected:
        # Closing a position reports the deal it affected, not the closing deal, and
        # that is the id a caller can look up afterwards.
        deal_id = affected[0].get("dealId", deal_id)
    direction = c.get("direction")
    return Order(
        status=status,
        id=deal_id,
        reference=c.get("dealReference"),
        symbol=c.get("epic"),
        direction=Direction(direction) if direction else None,
        size=c.get("size"),
        level=c.get("level"),
        reason=c.get("reason"),
    )


def working_order_from_raw(row: dict) -> WorkingOrder:
    """From a workingOrders[] row: ``{workingOrderData: {...}, marketData: {...}}``."""
    d = row.get("workingOrderData") or {}
    m = row.get("marketData") or {}
    return WorkingOrder(
        id=d["dealId"],
        symbol=d.get("epic") or m.get("epic", ""),
        direction=Direction(d["direction"]),
        size=d.get("orderSize", 0.0),
        order_type=OrderType(d.get("orderType", "LIMIT")),
        level=d.get("orderLevel"),
        good_till=d.get("timeInForce"),
        currency=d.get("currencyCode"),
    )

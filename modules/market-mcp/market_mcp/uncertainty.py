"""Sentences for what the numbers alone don't say — built once here so every tool
touching candles or coverage says the same thing the same way
(specs/market-mcp-answers).
"""

from __future__ import annotations

from datetime import datetime


def uncovered_sentence(gaps: list[tuple[datetime, datetime]]) -> str | None:
    """`None` when the whole requested range was verified — nothing to say."""
    if not gaps:
        return None
    spans = "; ".join(f"{start.isoformat()} to {end.isoformat()}" for start, end in gaps)
    return (
        f"The archive never verified {len(gaps)} stretch(es) of this range: {spans}. "
        "No candle there does not mean the market was quiet."
    )


def derived_sentence(derived: bool, resolution: str) -> str | None:
    if not derived:
        return None
    return (
        f"These {resolution} candles are computed from a finer series, not collected "
        "from the provider directly."
    )


def unsettled_sentence(warmup_bars: int | None) -> str:
    """An indicator result whose `settled` is false is still a value — market-data
    computed it from a series shorter than the formula wanted. `warmup_bars` is what
    the formula *needs*, not what was missing: the archive does not publish how many
    bars fell short, only how many the formula asked for
    (specs/market-mcp-answers, "Wskaźnik bez pełnej rozgrzewki").
    """
    if warmup_bars is None:
        return (
            "This value has not fully settled — the archive did not hold enough "
            "history before the requested range yet; treat it as provisional."
        )
    return (
        f"This value has not fully settled — it needs {warmup_bars} bars of warmup "
        "and the archive did not hold that many before the requested range; treat it "
        "as provisional."
    )


def forming_sentence(resolution: str) -> str:
    """Said whenever a price comes from a period that has not closed. Without it a model
    reports the period's high and low as its range, and both will still move
    (specs/market-mcp-tools, "Zakres okresu w toku MUST NOT być podany jako zakres
    zamknięty")."""
    return (
        f"This is the {resolution} period still being built — the price is current, but "
        "its high, low and volume will still move before the period closes. Do not quote "
        "them as the period's range."
    )


def no_live_price_sentence(symbol: str, state: str, market_open: bool | None = None) -> str:
    """Why there is no current price, in the words the state means.

    `market_closed` and `no_quotes` are the pair worth keeping apart: the first is the
    venue being shut, which is nobody's problem, and the second is the archive not
    receiving anything while it is open, which is somebody's problem right now
    (specs/market-mcp-tools, "Rynek otwarty, a ceny bieżącej nie ma").

    `no_quotes` covers one more case than its name suggests — the archive could not find
    out whether the market is open at all — and saying "the market is open" there would
    state as fact the one thing nobody established.
    """
    if state == "market_closed":
        return (
            f"{symbol}'s market is closed, so there is no price forming. The figure below "
            "is the last candle that closed, and its age says how long ago that was."
        )
    if state == "no_quotes" and market_open is True:
        return (
            f"{symbol}'s market is open and the archive is receiving nothing for it — "
            "collection has stopped, this is not a quiet market. The figure below is the "
            "last candle that closed; treat it as stale, not as current."
        )
    if state == "no_quotes":
        return (
            f"The archive is receiving nothing for {symbol}, and could not find out "
            "whether its market is open. Either the venue is shut or collection has "
            "stopped — this is not a quiet market either way. The figure below is the "
            "last candle that closed; treat it as stale, not as current."
        )
    return (
        f"{symbol} has no price forming because nobody is collecting it. See "
        "list_tracked_pairs for what is actually tracked."
    )


def empty_series_sentence(symbol: str, tracked: bool) -> str:
    """Distinguishes "nobody is collecting this pair" from "it is tracked, but this
    window has no candle" — the same empty list means two different things
    (specs/market-mcp-answers, "Trzy rodzaje 'nie wiem' są rozróżnione").
    """
    if tracked:
        return (
            f"{symbol} is tracked, but this window has no candle. Check "
            "describe_coverage — an unverified stretch here is not the same as a "
            "quiet market."
        )
    return (
        f"{symbol} has no candles because nobody is collecting it, not because the "
        "market was quiet. See list_tracked_pairs for what is actually tracked."
    )

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

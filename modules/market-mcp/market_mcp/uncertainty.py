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

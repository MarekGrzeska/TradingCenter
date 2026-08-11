"""Helpers every tool submodule needs, kept out of `__init__.py` so importing one
concern's tools does not pull the others in for nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from ..client import UpstreamClient
from ..errors import ToolRefusal

DEFAULT_WINDOW = timedelta(days=1)


def resolve_window(from_iso: str | None, to_iso: str | None) -> tuple[datetime, datetime]:
    """Mirrors market-data's own default (`candles.py`'s `_window`): the last day when
    neither bound is given, a naive instant read as UTC. Resolved here rather than left
    to market-data so this module always knows, and can echo, exactly what it asked
    for — never a guess at what the archive defaulted to on its side.
    """
    end = datetime.fromisoformat(to_iso) if to_iso else datetime.now(UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    start = datetime.fromisoformat(from_iso) if from_iso else end - DEFAULT_WINDOW
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    return start, end


async def is_tracked(upstream: UpstreamClient, symbol: str, resolution: str) -> bool:
    response = await upstream.get("/pairs")
    await raise_for_status(response)
    return any(
        row["symbol"] == symbol and row["resolution"] == resolution for row in response.json()
    )


async def raise_for_status(response: httpx.Response) -> None:
    """The archive's own refusal, not a generic HTTP error — its `detail` MUST reach
    the caller's tool reply (specs/market-mcp-answers, "Odmowa archiwum przepisana").
    """
    if not response.is_error:
        return
    try:
        detail = response.json().get("detail", response.text)
    except ValueError:
        detail = response.text
    raise ToolRefusal(f"market-data refused: {detail}")

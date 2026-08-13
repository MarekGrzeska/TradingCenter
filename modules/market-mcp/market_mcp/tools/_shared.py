"""Helpers every tool submodule needs, kept out of `__init__.py` so importing one
concern's tools does not pull the others in for nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from ..client import UpstreamClient
from ..errors import ToolRefusal

DEFAULT_WINDOW = timedelta(days=1)

# Applied to every `@mcp.tool()` in this package — a structural claim an MCP client
# can act on, not just a convention this module follows
# (specs/market-mcp-tools, "Zestaw narzędzi wyłącznie czyta").
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)


class WindowedOut(BaseModel):
    """The window an answer covers, for every output model that carries one.

    Both aliases, and the pair is load-bearing. FastMCP derives a tool's `outputSchema`
    from the model's *validation* schema and then serializes the reply with
    `by_alias=True`; the lowlevel server validates the second against the first. With
    `serialization_alias` alone the schema required `from_` while the reply carried
    `from`, and all four window-carrying tools refused their own answer with
    `Output validation error: 'from_' is a required property`. Nothing here caught it —
    `FastMCP.call_tool`, which every test uses, skips that check, so the tools were green
    in CI and broken on every real call (see `_check_output_schema` in the tests).

    `alias="from"` would say the same thing in one word, and pyright then synthesizes an
    `__init__` taking a parameter literally named `from` — unwritable, since it is a
    keyword — and rejects every construction in this package. Naming the two sides
    separately leaves the field name alone. `populate_by_name` keeps `from_=` accepted on
    the way in as well.
    """

    model_config = ConfigDict(populate_by_name=True)

    from_: datetime = Field(validation_alias="from", serialization_alias="from")
    to: datetime


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


async def tracked_pair(
    upstream: UpstreamClient, symbol: str, resolution: str
) -> dict[str, Any] | None:
    """The archive's own row for this pair, or None when it collects no such pair. Carries
    `latest_candle`, which is the only way to reach a candle older than a window without
    guessing how much older."""
    response = await upstream.get("/pairs")
    await raise_for_status(response)
    return next(
        (
            row
            for row in response.json()
            if row["symbol"] == symbol and row["resolution"] == resolution
        ),
        None,
    )


async def is_tracked(upstream: UpstreamClient, symbol: str, resolution: str) -> bool:
    return await tracked_pair(upstream, symbol, resolution) is not None


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

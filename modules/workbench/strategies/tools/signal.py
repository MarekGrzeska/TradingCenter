"""What the engine would do now — the one tool here a team gets beside reading (`strategies-tools`). It reads the
archive and the strategy, and writes nothing: no run, no trial, nothing the account sees."""

from __future__ import annotations

import time
from typing import Any

from mcp.server.fastmcp import FastMCP

from .. import signals
from ..archive import ArchiveUnavailable
from ._shared import READ_ONLY, ToolContext, refusal


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def strategy_signal(strategy_id: int, revision: int) -> dict[str, Any]:
        """What the backtest engine would do now for this revision, from the bar that closed last: `enter` (an order to
        place), `order_working`, `exit` (close the position), `hold`, or `none`. Check `bar_closed_at`: a bar that
        closed long ago is not this bar's decision. `position` is the engine's own, not the account's — compare it with
        the account. Size the order from the account's balance and `sizing` (e.g. size_for_margin), never invent one.
        Also: `order` (side, kind, price), `position` (side, entered_at, entry_price, stop, target), `exit_reason`,
        `window_from` (an engine position opened before it is not seen), `params`, `costs_source`."""
        async with ctx.state.pool.acquire() as conn:
            try:
                # A dict, as read_backtest's report is: a typed answer is its whole schema in every turn.
                found = await signals.signal(conn, ctx.state.archive, strategy_id, revision, int(time.time()))
                return found.model_dump(mode="json")
            except signals.SignalRefused as err:
                raise refusal(str(err)) from None
            except (ArchiveUnavailable, TimeoutError) as err:
                raise refusal(f"the signal could not be computed: {err or 'it took too long'}") from None

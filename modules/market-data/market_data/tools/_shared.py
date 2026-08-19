"""Helpers every tool submodule needs, kept out of `__init__.py` so importing one
concern's tools does not pull the others in for nothing.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from ..gateway import GatewayInstruments
from ..hub import Hub
from ..market_status import MarketStatus
from ..models import Resolution
from ..reads import read_pairs
from ..tracking import TrackedPairStatus

DEFAULT_WINDOW = timedelta(days=1)

# How long one candle of each resolution covers. Here rather than in one tool's module
# because two now need it: `indicators.py` to turn a bar count into a window, and
# `candles.py` to order a pair's resolutions from finest to coarsest.
PERIOD_SECONDS = {
    "MINUTE": 60,
    "MINUTE_5": 300,
    "MINUTE_15": 900,
    "MINUTE_30": 1800,
    "HOUR": 3600,
    "HOUR_4": 14400,
    "DAY": 86400,
    "WEEK": 604800,
}

# Applied to every `@mcp.tool()` in this package — a structural claim an MCP client
# can act on, not just a convention this module follows
# (specs/market-data-tools, "Zestaw narzędzi wyłącznie czyta").
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)


@dataclass(frozen=True)
class ToolContext:
    """What a tool needs from the running application, read when the tool is called.

    Lazily, and that is the whole point of the indirection: the tool surface is mounted in
    `create_app()`, while everything it reads is put on `app.state` by the lifespan, which
    has not run yet at mount time. Holding the app and reaching through it at call time is
    what lets the two happen in that order.
    """

    app: object

    @property
    def _state(self):
        return self.app.state  # pyright: ignore[reportAttributeAccessIssue]

    @property
    def pool(self):
        return self._state.pool

    @property
    def hub(self) -> Hub:
        return self._state.hub

    @property
    def instruments(self) -> GatewayInstruments:
        return self._state.instruments

    @property
    def market_status(self) -> MarketStatus:
        return self._state.market_status

    @property
    def indicator_limiter(self) -> asyncio.Semaphore:
        """The same ceiling the REST route holds, not a second one.

        Two entrances to the same computation with one semaphore between them; a tool that
        took its own would double the concurrency the archive was configured to allow, and
        nothing would report it — the machine would simply be slower under load.
        """
        return self._state.indicator_limiter


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
    """The window a tool answers over, resolved here rather than left to a default further
    in, so the answer can always echo exactly what it covered.

    Takes ISO strings because that is what an MCP client sends; `reads.window` takes
    instants and is what the REST route uses.
    """
    end = datetime.fromisoformat(to_iso) if to_iso else datetime.now(UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    start = datetime.fromisoformat(from_iso) if from_iso else end - DEFAULT_WINDOW
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    return start, end


async def tracked_pairs(ctx: ToolContext) -> list[TrackedPairStatus]:
    """Every tracked pair with its collection state — one read, shared by the callers below.

    The same answer `GET /pairs` builds its reply from. The 2-second memo the HTTP client
    used to keep is gone with the client: there is no request to spend here, only a query.
    """
    moment = datetime.now(UTC)
    async with ctx.pool.acquire() as conn:
        decided = await read_pairs(conn, ctx.instruments, ctx.market_status, moment)
    return [status.model_copy(update={"collection": collection}) for status, collection in decided]


async def tracked_pair(
    ctx: ToolContext, symbol: str, resolution: str
) -> TrackedPairStatus | None:
    """The archive's own row for this pair, or None when it collects no such pair. Carries
    `latest_candle`, which is the only way to reach a candle older than a window without
    guessing how much older."""
    return next(
        (
            pair
            for pair in await tracked_pairs(ctx)
            if pair.symbol == symbol and pair.resolution.value == resolution
        ),
        None,
    )


async def is_tracked(ctx: ToolContext, symbol: str, resolution: str) -> bool:
    return await tracked_pair(ctx, symbol, resolution) is not None


async def tracked_resolutions(ctx: ToolContext, symbol: str) -> list[str]:
    """Every resolution the archive collects this symbol at, finest first.

    For the caller that has no resolution of its own to offer: a pair tracked at HOUR and
    DAY answers nothing at MINUTE, and guessing the default is how a question about a
    tracked pair comes back empty.
    """
    found = [pair.resolution.value for pair in await tracked_pairs(ctx) if pair.symbol == symbol]
    return sorted(found, key=lambda r: PERIOD_SECONDS.get(r, 0))


def resolution_of(value: str) -> Resolution:
    """The archive's own enum, or a refusal naming what was asked for."""
    from .errors import ToolRefusal

    try:
        return Resolution(value)
    except ValueError as unknown:
        known = ", ".join(r.value for r in Resolution)
        raise ToolRefusal(f"unknown resolution {value!r}. The archive knows: {known}") from unknown

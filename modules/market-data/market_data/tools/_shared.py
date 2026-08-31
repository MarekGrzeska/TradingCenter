"""Helpers every tool submodule needs, kept out of `__init__.py` so importing one concern's tools
does not pull the others in for nothing."""

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

# How long one candle of each resolution covers. Here rather than in one tool's module because two
# need it: to turn a bar count into a window, and to order a pair's resolutions finest first.
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

# Applied to every `@mcp.tool()` in this package — a structural claim an MCP client can act on, not
# just a convention this module follows.
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)


@dataclass(frozen=True)
class ToolContext:
    """What a tool needs from the running application, read when the tool is called. Lazily: the surface
    is mounted in `create_app()` while everything it reads is put on `app.state` by the lifespan."""

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
        """The same ceiling the REST route holds, not a second one. A tool taking its own would double
        the concurrency the archive was configured to allow, and nothing would report it."""
        return self._state.indicator_limiter


class WindowedOut(BaseModel):
    """The window an answer covers. Both aliases, and the pair is load-bearing: FastMCP derives the
    `outputSchema` from the validation schema and serializes with `by_alias`, so one alone refuses itself."""

    model_config = ConfigDict(populate_by_name=True)

    from_: datetime = Field(validation_alias="from", serialization_alias="from")
    to: datetime


def resolve_window(from_iso: str | None, to_iso: str | None) -> tuple[datetime, datetime]:
    """The window a tool answers over, resolved here so the answer can echo exactly what it covered. The
    reversed-range refusal is raised here: in-process there is nothing to refuse it, and empty reads as quiet."""
    from .errors import ToolRefusal

    end = datetime.fromisoformat(to_iso) if to_iso else datetime.now(UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    start = datetime.fromisoformat(from_iso) if from_iso else end - DEFAULT_WINDOW
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end < start:
        raise ToolRefusal(
            f"`to` is before `from`: {start.isoformat()} to {end.isoformat()}. "
            "Swap the two bounds."
        )
    return start, end


async def tracked_pairs(ctx: ToolContext) -> list[TrackedPairStatus]:
    """Every tracked pair with its collection state — one read, shared by the callers below. The same
    answer `GET /pairs` builds its reply from; there is no request to spend, only a query."""
    moment = datetime.now(UTC)
    async with ctx.pool.acquire() as conn:
        decided = await read_pairs(conn, ctx.instruments, ctx.market_status, moment)
    return [status.model_copy(update={"collection": collection}) for status, collection in decided]


async def tracked_pair(
    ctx: ToolContext, symbol: str, resolution: str
) -> TrackedPairStatus | None:
    """The archive's own row for this pair, or None. Carries `latest_candle`, the only way to reach a
    candle older than a window without guessing how much older."""
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
    """Every resolution the archive collects this symbol at, finest first. For the caller with no
    resolution to offer: guessing the default is how a question about a tracked pair comes back empty."""
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

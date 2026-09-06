"""Reading deep history through the gateway's `/instruments/{symbol}/history`. No paging here: the
gateway already pages, anchors on data and owns the rate gate, so one long request goes out per fill."""

from __future__ import annotations

from datetime import datetime

import httpx
from pydantic import BaseModel, ValidationError

from ..errors import UnreadablePayload
from ..models import Candle, CandleSource, PriceSide, Resolution
from ..periods import from_iso
from ._http import get_json


class HistoryPage(BaseModel):
    """One answer from the gateway, as the archive reads it. `history_ended` is why this is a model
    rather than a list: it becomes the left edge of a coverage range."""

    symbol: str
    resolution: Resolution
    candles: list[Candle]
    requested: int
    # What the read cost upstream, passed through so an operator can see why a fill was
    # slow instead of guessing.
    requests: int
    history_ended: bool


class GatewayHistory:
    """The gateway's history endpoint, as this module uses it."""

    def __init__(self, base_url: str, client: httpx.AsyncClient) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client

    async def history(
        self,
        symbol: str,
        resolution: Resolution,
        bars: int,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> HistoryPage:
        """Reach back `bars` candles for one pair, ending at `before` and stopping at `after`. Not
        everything comes back closed, and `after` is the only way to bound a read in *time*."""
        url = f"{self._base_url}/instruments/{symbol}/history"
        params: dict[str, str | int] = {"resolution": resolution.value, "bars": bars}
        if before is not None:
            params["before"] = before.isoformat()
        if after is not None:
            params["after"] = after.isoformat()

        body = await get_json(
            self._client, url, params=params, what=f"{symbol} {resolution.value}"
        )
        try:
            payload = _CandleHistory.model_validate(body)
        except (ValueError, ValidationError) as err:
            raise UnreadablePayload(
                f"the gateway's history for {symbol} {resolution.value} did not match the "
                f"shape this module reads: {err}"
            ) from err

        candles = [
            Candle(
                symbol=symbol,
                resolution=payload.resolution,
                period_start=from_iso(row.ts),
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                volume=row.volume,
                price_side=PriceSide.BID,
                source=CandleSource.HISTORY,
                    # Read, not assumed. A read reaching the present brings back the period it is
                    # in, and stamping the lot as settled archived a half-finished price as a result.
                forming=row.forming,
            )
            for row in payload.candles
        ]
        # Sorted on the instant, not on the string the gateway sorted by: its sort is chronological
        # only while every timestamp carries the same zone marker, and some carry none.
        candles.sort(key=lambda candle: candle.period_start)

        return HistoryPage(
            symbol=symbol,
            resolution=payload.resolution,
            candles=candles,
            requested=payload.requested,
            requests=payload.requests,
            history_ended=payload.history_ended,
        )


class _Candle(BaseModel):
    """The gateway's candle, read only to be converted. Extra fields are ignored rather
    than refused: the gateway may add one without this module needing to care."""

    ts: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    # Defaulted, so a gateway too old to say still parses. The default is the reading this
    # module made for years anyway — it just used to be the only one available.
    forming: bool = False


class _CandleHistory(BaseModel):
    candles: list[_Candle]
    requested: int
    requests: int
    resolution: Resolution
    history_ended: bool = False

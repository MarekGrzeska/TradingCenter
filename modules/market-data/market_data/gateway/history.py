"""Reading deep history through the gateway's `/instruments/{symbol}/history`.

**No paging here, deliberately.** The gateway already pages past the provider's
thousand-candle ceiling, anchors its cursor on the oldest candle it actually received
rather than on the clock, and reports what the read cost. Repeating that would be a
second implementation of the same rules, drifting from the first — and it is the first
that owns the rate gate.

So one request goes out per fill, however deep, and it is a long one: the gateway
measures twenty thousand five-minute candles at thirty provider calls and twenty-six
seconds. The timeout below is sized for that, not for a local API.
"""

from __future__ import annotations

from datetime import datetime

import httpx
from pydantic import BaseModel, ValidationError

from ..errors import GatewayRefused, GatewayUnreachable, UnreadablePayload
from ..models import Candle, CandleSource, PriceSide, Resolution
from ..periods import from_iso

# A deep read is tens of provider calls behind one HTTP request, so the read timeout is
# minutes rather than seconds. Connect stays short: a gateway that is not listening
# should be reported as unreachable now, not after three minutes of waiting.
DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=300.0, write=10.0, pool=5.0)


def http_client(timeout: httpx.Timeout = DEFAULT_TIMEOUT) -> httpx.AsyncClient:
    """A client sized for deep reads. Owned by the caller, so a fill and an interactive
    request can share one connection pool rather than opening one each."""
    return httpx.AsyncClient(timeout=timeout)


class HistoryPage(BaseModel):
    """One answer from the gateway, as the archive reads it.

    `history_ended` is the whole reason this is a model rather than a list: it is the
    gateway saying the provider has nothing older, and it becomes the left edge of a
    coverage range. Discarding it would leave the module asking for data that does not
    exist, forever.
    """

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
        self, symbol: str, resolution: Resolution, bars: int, before: datetime | None = None
    ) -> HistoryPage:
        """Reach back `bars` candles for one pair, ending at `before` rather than now.

        Everything comes back closed, on the bid side, and marked as having come from a
        history read — which is what later lets a history value outrank a streamed one
        for the same period.

        `before` is what lets a chunk (`jobs/plan.py`) ask for a window that ended
        months or years ago instead of always reaching back from the present — see
        `capital-market-data` spec, "Głęboki odczyt zaczyna się w dowolnym momencie".
        """
        url = f"{self._base_url}/instruments/{symbol}/history"
        params: dict[str, str | int] = {"resolution": resolution.value, "bars": bars}
        if before is not None:
            params["before"] = before.isoformat()

        try:
            response = await self._client.get(url, params=params)
        except httpx.RequestError as err:
            raise GatewayUnreachable(
                f"the gateway did not answer for {symbol} {resolution.value}: {err}"
            ) from err

        if response.is_error:
            raise GatewayRefused(response.status_code, _detail(response))

        try:
            payload = _CandleHistory.model_validate(response.json())
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
                forming=False,
            )
            for row in payload.candles
        ]
        # Sorted on the instant, not on the string the gateway sorted by. Its sort is
        # chronological only while every timestamp carries the same zone marker, and a
        # candle the provider gave no `snapshotTimeUTC` for carries none — one of those
        # in a page puts the string order and the time order at odds.
        candles.sort(key=lambda candle: candle.period_start)

        return HistoryPage(
            symbol=symbol,
            resolution=payload.resolution,
            candles=candles,
            requested=payload.requested,
            requests=payload.requests,
            history_ended=payload.history_ended,
        )


def _detail(response: httpx.Response) -> str:
    """What the gateway said. Its error handler puts the cause in `detail`; anything
    else is a failure that never reached that handler, so the body is read raw."""
    try:
        body = response.json()
    except ValueError:
        return response.text.strip() or response.reason_phrase
    if isinstance(body, dict) and isinstance(body.get("detail"), str):
        return body["detail"]
    return str(body)


class _Candle(BaseModel):
    """The gateway's candle, read only to be converted. Extra fields are ignored rather
    than refused: the gateway may add one without this module needing to care."""

    ts: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None


class _CandleHistory(BaseModel):
    candles: list[_Candle]
    requested: int
    requests: int
    resolution: Resolution
    history_ended: bool = False

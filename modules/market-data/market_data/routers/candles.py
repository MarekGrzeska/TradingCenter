"""Reading a range, and what the archive never looked at."""

from __future__ import annotations

from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
)

from ..contract import (
    CandleOut,
    CandlesOut,
    CoverageOut,
    FormingCandleOut,
    FormingState,
    PairCoverageOut,
    Problem,
    Uncovered,
)
from ..hub import Hub
from ..models import PriceSide, Resolution
from ..reads import (
    WindowRejected,
    read_forming,
    read_pair_coverage,
    read_series,
    window,
)
from .deps import hub_over_http, pool

DERIVED_NOTE = (
    "Resolutions between MINUTE_5 and HOUR_4 are computed from the minute series rather "
    "than collected separately — the provider serves 1000 candles per request at ten "
    "requests a second, so fetching each one costs its own traffic for data the finest "
    "already implies. MINUTE, DAY and WEEK come from the provider: a daily boundary "
    "follows the venue's session, not the clock."
)

router = APIRouter()


# --- candles ---


@router.get(
    "/candles/{symbol}",
    tags=["candles"],
    response_model=CandlesOut,
    responses={422: {"model": Problem}},
    summary="Candles for one pair over a time range",
    description=(
        "Answers with the series and, separately, the stretches of the requested range "
        "the archive never verified. Those are not the same as periods with no candle: a "
        "closed market has no candle either, and only one of the two is missing data.\n\n"
        + DERIVED_NOTE
    ),
)
async def candles(
    symbol: str,
    resolution: Resolution = Query(Resolution.MINUTE),
    from_: datetime | None = Query(None, alias="from", description="inclusive, UTC"),
    to: datetime | None = Query(None, description="exclusive, UTC"),
    db=Depends(pool),
) -> CandlesOut:
    start, end = _window(from_, to)

    async with db.acquire() as conn:
        series = await read_series(conn, symbol, resolution, start, end)

    return CandlesOut(
        symbol=symbol,
        resolution=resolution,
        price_side=PriceSide.BID,
        derived=series.derived,
        candles=[CandleOut.of(candle) for candle in series.candles],
        uncovered=[
            Uncovered(from_=gap_start, to=gap_end) for gap_start, gap_end in series.uncovered
        ],
    )


@router.get(
    "/candles/{symbol}/forming",
    tags=["candles"],
    response_model=FormingCandleOut,
    summary="The period being built right now, for one pair",
    description=(
        "The current price, as the candle the archive is building this instant — the same "
        "one a subscription's snapshot carries, without the handshake a subscription "
        "costs. Nothing here is stored: a forming candle changes with every quote and "
        "understates its own range until the period closes.\n\n"
        "Omit `resolution` and the archive answers from the finest one that actually has "
        "quotes arriving, which is not the same as the finest one tracked — a stalled "
        "minute feed on a pair also tracked hourly still has a price. Name one and it is "
        "honoured.\n\n"
        "An answer with no candle says which of three reasons it is: nobody collects this "
        "symbol, the market is shut, or it is open and nothing is arriving anyway. The "
        "last one is a collection failure, and it is the reason this is not simply a "
        "nullable candle."
    ),
)
async def forming_candle(
    symbol: str,
    request: Request,
    resolution: Resolution | None = Query(
        None, description="omit to let the archive pick the finest live one"
    ),
    the_hub: Hub = Depends(hub_over_http),
    db=Depends(pool),
) -> FormingCandleOut:
    async with db.acquire() as conn:
        forming = await read_forming(
            conn,
            the_hub,
            request.app.state.instruments,
            request.app.state.market_status,
            symbol,
            resolution,
        )

    return FormingCandleOut(
        symbol=symbol,
        resolution=forming.resolution,
        price_side=PriceSide.BID,
        state=FormingState(forming.state.value),
        candle=CandleOut.of(forming.candle) if forming.candle else None,
        market_open=forming.market_open,
    )


@router.get(
    "/coverage/{symbol}",
    tags=["candles"],
    response_model=PairCoverageOut,
    summary="What the archive has verified for one pair",
)
async def coverage(
    symbol: str, resolution: Resolution = Query(Resolution.MINUTE), db=Depends(pool)
) -> PairCoverageOut:
    async with db.acquire() as conn:
        found = await read_pair_coverage(conn, symbol, resolution)

    return PairCoverageOut(
        symbol=symbol,
        resolution=resolution,
        ranges=[
            CoverageOut(from_=r.range_start, to=r.range_end, history_ended=r.history_ended)
            for r in found.ranges
        ],
        earliest_reachable=found.earliest_reachable,
    )


def _window(from_: datetime | None, to: datetime | None) -> tuple[datetime, datetime]:
    """`reads.window`, with its refusal spelled as this transport spells refusals.

    A range whose end precedes its start is the request being wrong, not the archive, and
    answering 500 would send a caller looking for a fault here.
    """
    try:
        return window(from_, to)
    except WindowRejected as refused:
        raise HTTPException(status_code=422, detail=str(refused)) from refused

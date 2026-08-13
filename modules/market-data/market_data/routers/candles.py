"""Reading a range, and what the archive never looked at."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

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
from ..coverage import earliest_reachable, read_coverage, uncovered_within
from ..hub import Hub
from ..models import Candle, PriceSide, Resolution
from ..rollups import DERIVABLE, DerivedCandle, read_derived
from ..store import read_candles
from ..tracking import read_tracked
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
    start, end = _window(from_, to, resolution)

    async with db.acquire() as conn:
        # Collected beats computed, and the order matters more than it looks. A
        # resolution being *derivable* does not mean this pair was derived: an operator
        # may track a pair at HOUR, in which case ingest fetches and stores the
        # provider's own hourly candles and nothing ever builds a rollup for it, because
        # rollups are refreshed off the minute series that pair does not have. Reading
        # the rollup table unconditionally answered such a pair with an empty series
        # while coverage said the range was verified — which reads as "the market was
        # shut all day", the one confident wrong answer this module exists to prevent.
        series: Sequence[Candle | DerivedCandle] = await read_candles(
            conn, symbol, resolution, start, end
        )
        derived = False
        if not series and resolution in DERIVABLE:
            series = await read_derived(conn, symbol, resolution, start, end)
            derived = True
        gaps = await uncovered_within(conn, symbol, resolution, start, end)

    return CandlesOut(
        symbol=symbol,
        resolution=resolution,
        price_side=PriceSide.BID,
        derived=derived,
        candles=[CandleOut.of(candle) for candle in series],
        uncovered=[Uncovered(from_=gap_start, to=gap_end) for gap_start, gap_end in gaps],
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
        tracked = [pair for pair in await read_tracked(conn) if pair.symbol == symbol]

    if not tracked:
        return FormingCandleOut(
            symbol=symbol,
            resolution=resolution,
            price_side=PriceSide.BID,
            state=FormingState.NOT_TRACKED,
        )

    # Asked for even when a candle is found: a price with no session behind it cannot be
    # told from a price that stopped moving an hour ago, and this answer is cached for a
    # minute per symbol either way (`market_status.py`).
    _, market_open = await request.app.state.market_status.of(
        request.app.state.instruments, symbol
    )

    if resolution is not None:
        candle = the_hub.forming(symbol, resolution)
        answered_with = resolution
    else:
        answered_with = next(iter(the_hub.forming_resolutions(symbol)), None)
        candle = the_hub.forming(symbol, answered_with) if answered_with else None

    if candle is None:
        return FormingCandleOut(
            symbol=symbol,
            resolution=resolution,
            price_side=PriceSide.BID,
            # `market_open is None` — the gateway would not say — falls to `no_quotes`
            # rather than to `market_closed`: claiming a closed market on the strength of
            # an unanswered question is the one wrong answer here that reads as certain.
            state=(
                FormingState.MARKET_CLOSED if market_open is False else FormingState.NO_QUOTES
            ),
            market_open=market_open,
        )

    return FormingCandleOut(
        symbol=symbol,
        resolution=answered_with,
        price_side=PriceSide.BID,
        state=FormingState.FORMING,
        candle=CandleOut.of(candle),
        market_open=market_open,
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
        ranges = await read_coverage(conn, symbol, resolution)
        boundary = await earliest_reachable(conn, symbol, resolution)

    return PairCoverageOut(
        symbol=symbol,
        resolution=resolution,
        ranges=[
            CoverageOut(from_=r.range_start, to=r.range_end, history_ended=r.history_ended)
            for r in ranges
        ],
        earliest_reachable=boundary,
    )



def _window(
    from_: datetime | None, to: datetime | None, resolution: Resolution
) -> tuple[datetime, datetime]:
    """The requested range, with defaults and both ends carrying a zone.

    A naive bound is read as UTC rather than refused: it is the commonest way to write one
    by hand, and the archive stores instants, so the alternative is a 422 for something
    that has exactly one sensible reading.
    """
    end = to or datetime.now(UTC)
    start = from_ or end - timedelta(days=1)
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    if end < start:
        # A refusal, not a failure. The request is the thing that is wrong, and answering
        # 500 would send a caller looking for a fault in the archive.
        raise HTTPException(
            status_code=422,
            detail=f"`to` is before `from`: {start.isoformat()} to {end.isoformat()}",
        )
    return start, end

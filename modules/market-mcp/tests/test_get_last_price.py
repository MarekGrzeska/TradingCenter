"""What a pair costs now, and the four different reasons it might not be sayable.

The tool reads `/candles/{symbol}/forming` first and falls back to the settled series
only when that answers with no candle. Every test here mocks both roads, because the
interesting cases are the ones where the two disagree.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import respx

BASE = "http://127.0.0.1:8020"


def _forming_response(
    state: str,
    *,
    resolution: str | None = None,
    close: float | None = None,
    time: datetime | None = None,
    market_open: bool | None = None,
):
    candle = None
    if close is not None:
        moment = time or datetime.now(UTC)
        candle = {
            "time": moment.isoformat(),
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1,
        }
    return httpx.Response(
        200,
        json={
            "symbol": "US100",
            "resolution": resolution,
            "price_side": "bid",
            "state": state,
            "candle": candle,
            "market_open": market_open,
        },
    )


def _candles_response(candles: list[dict], derived: bool = False):
    return httpx.Response(
        200,
        json={
            "symbol": "US100",
            "resolution": "MINUTE",
            "price_side": "BID",
            "derived": derived,
            "candles": candles,
            "uncovered": [],
        },
    )


def _settled(moment: datetime, close: float):
    return _candles_response(
        [
            {
                "time": moment.isoformat(),
                "open": 100,
                "high": 101,
                "low": 99,
                "close": close,
                "volume": 1,
            }
        ]
    )


def _pairs_response(resolutions: dict[str, str | None]):
    """`{resolution: latest_candle iso or None}` — `/pairs` cut to the fields this tool
    reads."""
    return httpx.Response(
        200,
        json=[
            {
                "symbol": "US100",
                "resolution": resolution,
                "collection": "collecting",
                "candle_count": 191,
                "latest_candle": latest,
            }
            for resolution, latest in resolutions.items()
        ],
    )


@respx.mock
async def test_a_forming_period_is_the_price_now(server) -> None:
    # specs/market-mcp-tools, "Cena w trakcie sesji"
    mcp, upstream = server
    respx.get(f"{BASE}/candles/US100/forming").mock(
        return_value=_forming_response(
            "forming", resolution="MINUTE", close=29774.5, market_open=True
        )
    )

    _content, structured = await mcp.call_tool("get_last_price", {"symbol": "US100"})

    assert structured["close"] == 29774.5
    assert structured["forming"] is True
    assert structured["resolution"] == "MINUTE"
    assert structured["age_seconds"] < 60
    assert structured["market_open"] is True
    await upstream.aclose()


@respx.mock
async def test_a_forming_price_says_its_range_is_not_settled(server) -> None:
    """A model quoting the forming period's high and low as the period's range would be
    wrong before the period ends."""
    mcp, upstream = server
    respx.get(f"{BASE}/candles/US100/forming").mock(
        return_value=_forming_response(
            "forming", resolution="HOUR", close=29774.5, market_open=True
        )
    )

    _content, structured = await mcp.call_tool("get_last_price", {"symbol": "US100"})

    notes = " ".join(structured["notes"])
    assert "will still move" in notes
    assert "HOUR" in notes
    await upstream.aclose()


@respx.mock
async def test_a_named_resolution_is_passed_to_the_archive(server) -> None:
    mcp, upstream = server
    route = respx.get(f"{BASE}/candles/US100/forming").mock(
        return_value=_forming_response("forming", resolution="DAY", close=29774.5, market_open=True)
    )

    _content, structured = await mcp.call_tool(
        "get_last_price", {"symbol": "US100", "resolution": "DAY"}
    )

    assert route.calls[0].request.url.params["resolution"] == "DAY"
    assert structured["resolution"] == "DAY"
    await upstream.aclose()


@respx.mock
async def test_no_resolution_lets_the_archive_choose(server) -> None:
    mcp, upstream = server
    route = respx.get(f"{BASE}/candles/US100/forming").mock(
        return_value=_forming_response(
            "forming", resolution="HOUR", close=29774.5, market_open=True
        )
    )

    _content, structured = await mcp.call_tool("get_last_price", {"symbol": "US100"})

    # Nothing is guessed on this side: the archive knows which feed is live, and says
    # which one it answered from.
    assert "resolution" not in route.calls[0].request.url.params
    assert structured["resolution"] == "HOUR"
    await upstream.aclose()


@respx.mock
async def test_a_closed_market_falls_back_to_the_last_settled_candle(server) -> None:
    # specs/market-mcp-tools, "Cena po zamknięciu rynku"
    mcp, upstream = server
    moment = datetime.now(UTC) - timedelta(days=3)
    respx.get(f"{BASE}/candles/US100/forming").mock(
        return_value=_forming_response("market_closed", market_open=False)
    )
    respx.get(f"{BASE}/pairs").mock(return_value=_pairs_response({"DAY": moment.isoformat()}))
    respx.get(f"{BASE}/candles/US100").mock(return_value=_settled(moment, 29698.2))

    _content, structured = await mcp.call_tool("get_last_price", {"symbol": "US100"})

    assert structured["close"] == 29698.2
    assert structured["forming"] is False
    assert structured["resolution"] == "DAY"
    assert structured["age_seconds"] > timedelta(days=2).total_seconds()
    assert any("market is closed" in note for note in structured["notes"])
    await upstream.aclose()


@respx.mock
async def test_an_open_market_with_no_quotes_is_named_as_stalled_collection(server) -> None:
    """specs/market-mcp-tools, "Rynek otwarty, a ceny bieżącej nie ma" — the one empty
    answer that is somebody's problem right now."""
    mcp, upstream = server
    moment = datetime.now(UTC) - timedelta(hours=2)
    respx.get(f"{BASE}/candles/US100/forming").mock(
        return_value=_forming_response("no_quotes", market_open=True)
    )
    respx.get(f"{BASE}/pairs").mock(return_value=_pairs_response({"MINUTE": moment.isoformat()}))
    respx.get(f"{BASE}/candles/US100").mock(return_value=_settled(moment, 29700.0))

    _content, structured = await mcp.call_tool("get_last_price", {"symbol": "US100"})

    assert structured["close"] == 29700.0
    assert structured["forming"] is False
    notes = " ".join(structured["notes"])
    assert "collection has stopped" in notes
    assert "not a quiet market" in notes
    assert "treat it as stale" in notes
    await upstream.aclose()


@respx.mock
async def test_a_silent_gateway_is_not_reported_as_an_open_market(server) -> None:
    """`no_quotes` covers one more case than its name says: the archive could not find out
    whether the market is open. Saying "the market is open" there would state as fact the
    one thing nobody established."""
    mcp, upstream = server
    moment = datetime.now(UTC) - timedelta(hours=2)
    respx.get(f"{BASE}/candles/US100/forming").mock(
        return_value=_forming_response("no_quotes", market_open=None)
    )
    respx.get(f"{BASE}/pairs").mock(return_value=_pairs_response({"MINUTE": moment.isoformat()}))
    respx.get(f"{BASE}/candles/US100").mock(return_value=_settled(moment, 29700.0))

    _content, structured = await mcp.call_tool("get_last_price", {"symbol": "US100"})

    notes = " ".join(structured["notes"])
    assert "could not find out" in notes
    # The phrase the open-market branch uses — its absence is the assertion, since the
    # sentence above does mention the market being open as the thing nobody established.
    assert "market is open and the archive is receiving nothing" not in notes
    assert "not a quiet market" in notes
    await upstream.aclose()


@respx.mock
async def test_the_finest_tracked_resolution_answers_when_none_was_asked_for(server) -> None:
    mcp, upstream = server
    moment = datetime.now(UTC) - timedelta(hours=2)
    respx.get(f"{BASE}/candles/US100/forming").mock(
        return_value=_forming_response("market_closed", market_open=False)
    )
    # Deliberately out of order, and MINUTE is not among them: the pair is tracked at HOUR
    # and DAY, and a tool defaulting to MINUTE would answer nothing at all.
    respx.get(f"{BASE}/pairs").mock(
        return_value=_pairs_response({"DAY": moment.isoformat(), "HOUR": moment.isoformat()})
    )
    route = respx.get(f"{BASE}/candles/US100").mock(return_value=_settled(moment, 29700.0))

    _content, structured = await mcp.call_tool("get_last_price", {"symbol": "US100"})

    assert structured["resolution"] == "HOUR"
    assert route.calls[0].request.url.params["resolution"] == "HOUR"
    await upstream.aclose()


@respx.mock
async def test_an_untracked_pair_says_nobody_collects_it(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/candles/US100/forming").mock(return_value=_forming_response("not_tracked"))

    _content, structured = await mcp.call_tool("get_last_price", {"symbol": "US100"})

    assert structured["close"] is None
    assert structured["time"] is None
    assert any("nobody is collecting it" in note for note in structured["notes"])
    await upstream.aclose()


@respx.mock
async def test_a_tracked_pair_with_no_candle_at_all_still_answers(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/candles/US100/forming").mock(
        return_value=_forming_response("market_closed", market_open=False)
    )
    respx.get(f"{BASE}/pairs").mock(return_value=_pairs_response({"DAY": None}))

    _content, structured = await mcp.call_tool("get_last_price", {"symbol": "US100"})

    assert structured["time"] is None
    assert any("market is closed" in note for note in structured["notes"])
    assert any("this window has no candle" in note for note in structured["notes"])
    await upstream.aclose()

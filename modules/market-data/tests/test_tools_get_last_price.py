"""What a pair costs now, and the four different reasons it might not be sayable. Every test sets both
roads, because the interesting cases are the ones where the forming period and the settled candle disagree."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tools_double import candle, forming, tracked

from market_data.models import Resolution
from market_data.reads import FormingState, Series


def _settled(moment: datetime, close: float) -> Series:
    return Series(
        candles=[candle(moment, close=close)],
        derived=False,
        uncovered=[],
    )


async def test_a_forming_period_is_the_price_now(tool_server, archive) -> None:
    # specs/market-data-tools, "Cena w trakcie sesji"
    archive.forming = forming(
        FormingState.FORMING, resolution=Resolution.MINUTE, close=29774.5, market_open=True
    )

    _content, structured = await tool_server.call_tool("get_last_price", {"symbol": "US100"})

    assert structured["close"] == 29774.5
    assert structured["forming"] is True
    assert structured["resolution"] == "MINUTE"
    assert structured["age_seconds"] < 60
    assert structured["market_open"] is True


async def test_a_forming_price_says_its_range_is_not_settled(tool_server, archive) -> None:
    """A model quoting the forming period's high and low as the period's range would be
    wrong before the period ends."""
    archive.forming = forming(
        FormingState.FORMING, resolution=Resolution.HOUR, close=29774.5, market_open=True
    )

    _content, structured = await tool_server.call_tool("get_last_price", {"symbol": "US100"})

    notes = " ".join(structured["notes"])
    assert "will still move" in notes
    assert "HOUR" in notes


async def test_a_named_resolution_is_passed_to_the_archive(tool_server, archive) -> None:
    archive.forming = forming(
        FormingState.FORMING, resolution=Resolution.DAY, close=29774.5, market_open=True
    )

    _content, structured = await tool_server.call_tool(
        "get_last_price", {"symbol": "US100", "resolution": "DAY"}
    )

    assert archive.reads[0] == ("forming", "US100", Resolution.DAY)
    assert structured["resolution"] == "DAY"


async def test_no_resolution_lets_the_archive_choose(tool_server, archive) -> None:
    archive.forming = forming(
        FormingState.FORMING, resolution=Resolution.HOUR, close=29774.5, market_open=True
    )

    _content, structured = await tool_server.call_tool("get_last_price", {"symbol": "US100"})

    # Nothing is guessed on this side: the archive knows which feed is live, and says
    # which one it answered from.
    assert archive.reads[0] == ("forming", "US100", None)
    assert structured["resolution"] == "HOUR"


async def test_a_closed_market_falls_back_to_the_last_settled_candle(tool_server, archive) -> None:
    # specs/market-data-tools, "Cena po zamknięciu rynku"
    moment = datetime.now(UTC) - timedelta(days=3)
    archive.forming = forming(FormingState.MARKET_CLOSED, market_open=False)
    archive.pairs = [tracked(resolution=Resolution.DAY, latest_candle=moment)]
    archive.series = _settled(moment, 29698.2)

    _content, structured = await tool_server.call_tool("get_last_price", {"symbol": "US100"})

    assert structured["close"] == 29698.2
    assert structured["forming"] is False
    assert structured["resolution"] == "DAY"
    assert structured["age_seconds"] > timedelta(days=2).total_seconds()
    assert any("market is closed" in note for note in structured["notes"])


async def test_an_open_market_with_no_quotes_is_named_as_stalled_collection(
    tool_server, archive
) -> None:
    """specs/market-data-tools, "Rynek otwarty, a ceny bieżącej nie ma" — the one empty
    answer that is somebody's problem right now."""
    moment = datetime.now(UTC) - timedelta(hours=2)
    archive.forming = forming(FormingState.NO_QUOTES, market_open=True)
    archive.pairs = [tracked(resolution=Resolution.MINUTE, latest_candle=moment)]
    archive.series = _settled(moment, 29700.0)

    _content, structured = await tool_server.call_tool("get_last_price", {"symbol": "US100"})

    assert structured["close"] == 29700.0
    assert structured["forming"] is False
    notes = " ".join(structured["notes"])
    assert "collection has stopped" in notes
    assert "not a quiet market" in notes
    assert "treat it as stale" in notes


async def test_a_silent_gateway_is_not_reported_as_an_open_market(tool_server, archive) -> None:
    """`no_quotes` covers one more case than its name says: the archive could not find out whether the
    market is open, and saying it is would state as fact the one thing nobody established."""
    moment = datetime.now(UTC) - timedelta(hours=2)
    archive.forming = forming(FormingState.NO_QUOTES, market_open=None)
    archive.pairs = [tracked(resolution=Resolution.MINUTE, latest_candle=moment)]
    archive.series = _settled(moment, 29700.0)

    _content, structured = await tool_server.call_tool("get_last_price", {"symbol": "US100"})

    notes = " ".join(structured["notes"])
    assert "could not find out" in notes
    # The phrase the open-market branch uses — its absence is the assertion, since the
    # sentence above does mention the market being open as the thing nobody established.
    assert "market is open and the archive is receiving nothing" not in notes
    assert "not a quiet market" in notes


async def test_the_finest_tracked_resolution_answers_when_none_was_asked_for(
    tool_server, archive
) -> None:
    moment = datetime.now(UTC) - timedelta(hours=2)
    archive.forming = forming(FormingState.MARKET_CLOSED, market_open=False)
    # Deliberately out of order, and MINUTE is not among them: the pair is tracked at HOUR
    # and DAY, and a tool defaulting to MINUTE would answer nothing at all.
    archive.pairs = [
        tracked(resolution=Resolution.DAY, latest_candle=moment),
        tracked(resolution=Resolution.HOUR, latest_candle=moment),
    ]
    archive.series = _settled(moment, 29700.0)

    _content, structured = await tool_server.call_tool("get_last_price", {"symbol": "US100"})

    assert structured["resolution"] == "HOUR"
    series_read = next(read for read in archive.reads if read[0] == "series")
    assert series_read[2] is Resolution.HOUR


async def test_an_untracked_pair_says_nobody_collects_it(tool_server, archive) -> None:
    archive.forming = forming(FormingState.NOT_TRACKED)

    _content, structured = await tool_server.call_tool("get_last_price", {"symbol": "US100"})

    assert structured["close"] is None
    assert structured["time"] is None
    assert any("nobody is collecting it" in note for note in structured["notes"])


async def test_a_tracked_pair_with_no_candle_at_all_still_answers(tool_server, archive) -> None:
    archive.forming = forming(FormingState.MARKET_CLOSED, market_open=False)
    archive.pairs = [tracked(resolution=Resolution.DAY, latest_candle=None)]

    _content, structured = await tool_server.call_tool("get_last_price", {"symbol": "US100"})

    assert structured["time"] is None
    assert any("market is closed" in note for note in structured["notes"])
    assert any("this window has no candle" in note for note in structured["notes"])

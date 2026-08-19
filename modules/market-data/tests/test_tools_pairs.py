from __future__ import annotations

from datetime import UTC, datetime

from tools_double import tracked

from market_data.models import Resolution
from market_data.tools.pairs import _pair_out, _worst_collection
from market_data.tracking import CollectionState


def test_all_collecting_summarises_as_collecting() -> None:
    assert _worst_collection(["collecting", "collecting", "collecting"]) == "collecting"


def test_one_stalled_resolution_decides_the_symbol() -> None:
    """The whole reason this summary takes the worst rather than the commonest: six
    healthy timeframes must not hide the seventh that stopped."""
    assert _worst_collection(["collecting"] * 6 + ["stalled"]) == "stalled"


def test_market_closed_loses_to_never_collected() -> None:
    assert _worst_collection(["market_closed", "never_collected"]) == "never_collected"


def test_a_state_this_list_has_never_heard_of_ranks_worst() -> None:
    """A state added to `CollectionState` and not to this list is not a reason to report
    the symbol as healthy on its behalf — the summary would then be silently wrong in the
    one direction that matters. The two live in one module now, so this is the case where
    they were changed together and this list was not."""
    assert _worst_collection(["collecting", "paused_by_operator"]) == "paused_by_operator"


def test_pair_out_computes_age_from_latest_candle() -> None:
    out = _pair_out(tracked(candle_count=42, latest_candle=datetime(2020, 1, 1, tzinfo=UTC)))
    assert out.symbol == "US100"
    assert out.latest_candle_age_seconds is not None
    assert out.latest_candle_age_seconds > 0


def test_pair_out_with_no_candles_has_no_age() -> None:
    out = _pair_out(
        tracked(collection=CollectionState.NEVER_COLLECTED, candle_count=0, latest_candle=None)
    )
    assert out.latest_candle_age_seconds is None


async def test_one_row_per_symbol_sorted_and_without_resolutions(tool_server, archive) -> None:
    archive.pairs = [
        tracked("US100", Resolution.MINUTE_5),
        tracked("US100", Resolution.HOUR),
        tracked("GOLD", Resolution.MINUTE_5),
        tracked("GOLD", Resolution.WEEK),
        # Out of order on purpose: a resolution added later lands at the end, and the
        # fold must not depend on rows of one symbol being adjacent.
        tracked("US100", Resolution.MINUTE),
    ]

    _content, structured = await tool_server.call_tool("list_tracked_symbols", {})

    assert structured["result"] == [
        {"symbol": "GOLD", "collection": "collecting"},
        {"symbol": "US100", "collection": "collecting"},
    ]


async def test_the_symbol_carries_its_least_healthy_resolution(tool_server, archive) -> None:
    archive.pairs = [
        tracked("US100", Resolution.MINUTE_5, CollectionState.COLLECTING),
        tracked("US100", Resolution.HOUR, CollectionState.STALLED),
        tracked("GOLD", Resolution.MINUTE_5, CollectionState.MARKET_CLOSED),
    ]

    _content, structured = await tool_server.call_tool("list_tracked_symbols", {})

    assert structured["result"] == [
        {"symbol": "GOLD", "collection": "market_closed"},
        {"symbol": "US100", "collection": "stalled"},
    ]


async def test_nothing_tracked_is_an_empty_list_not_a_refusal(tool_server, archive) -> None:
    archive.pairs = []

    _content, structured = await tool_server.call_tool("list_tracked_symbols", {})

    assert structured == {"result": []}


async def test_list_tracked_pairs_reads_the_archive(tool_server, archive) -> None:
    archive.pairs = [
        tracked(candle_count=42, latest_candle=datetime(2020, 1, 1, tzinfo=UTC))
    ]

    _content, structured = await tool_server.call_tool("list_tracked_pairs", {})

    [pair] = structured["result"]
    assert pair["symbol"] == "US100"
    assert pair["resolution"] == "MINUTE"
    assert pair["collection"] == "collecting"
    assert pair["candle_count"] == 42
    assert pair["latest_candle_age_seconds"] > 0


async def test_list_tracked_pairs_with_no_pairs(tool_server, archive) -> None:
    archive.pairs = []

    _content, structured = await tool_server.call_tool("list_tracked_pairs", {})

    assert structured == {"result": []}

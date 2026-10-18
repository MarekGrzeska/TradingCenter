"""What the tool surface announces, what it costs to announce it, and the line that makes this set different from the post
archive's: it adds to a list, and it never takes anything off."""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta

import pytest

from youtube_data import store
from youtube_data.analysis import Reading
from youtube_data.providers.base import VideoRef

from .harness import GOLD, MARKETS, Rig

pytestmark = pytest.mark.db

READS = {"youtube_archive_status", "recent_videos", "read_video", "read_transcript", "instrument_sentiment"}
ADDS = {"follow_channel", "add_topic", "analyse_video"}
EXPECTED_TOOLS = READS | ADDS | {"search_youtube"}

# Characters of the serialized `list_tools()`, read by a client before every turn — the surface a conversation pays for it.
# Measured 18 381 on 29 September 2026 for ten tools — the post archive's four were 7 771, the prediction markets' twelve
# 18 250 — with headroom of about a tenth.
SURFACE_CEILING_CHARS = 20_500


@pytest.fixture
async def rig(pool) -> Rig:
    return Rig(pool)


@pytest.fixture
async def tools(app, rig):
    """The FastMCP server this package publishes, built from the same application `create_app()` builds and wired to a real
    database and the simulation — a server assembled here would be a ceiling on nothing."""
    app.state.pool = rig.pool
    app.state.settings = rig.settings
    app.state.providers = rig.providers
    app.state.alerts = None
    return app.state.mcp_server


async def call(tools, name: str, **arguments):
    _, structured = await tools.call_tool(name, arguments)
    return structured["result"] if set(structured) == {"result"} else structured


async def follow_and_read(tools, rig: Rig, *channels: str) -> None:
    for channel in channels:
        await call(tools, "follow_channel", reference=channel)
    await rig.tick()


# --- the surface ----------------------------------------------------------------------------------------------------


async def test_the_expected_tools_and_no_others(tools) -> None:
    assert {tool.name for tool in await tools.list_tools()} == EXPECTED_TOOLS


async def test_the_surface_adds_and_never_removes(tools) -> None:
    """The annotation is a structural claim an MCP client can act on, so it has to be exact. Taking a channel off the list is
    the operator's, through a route: the agent that could take one off could take the one the operator cared about."""
    for tool in await tools.list_tools():
        assert tool.annotations is not None, tool.name
        assert tool.annotations.destructiveHint is False, tool.name
        assert (tool.annotations.readOnlyHint is False) == (tool.name in ADDS), tool.name
    forbidden = ("remove", "delete", "unfollow", "drop", "purge")
    assert not [t.name for t in await tools.list_tools() if any(word in t.name for word in forbidden)]


async def test_the_surface_stays_within_what_a_conversation_pays_for_it(tools) -> None:
    payload = json.dumps([tool.model_dump() for tool in await tools.list_tools()], ensure_ascii=False)

    assert len(payload) <= SURFACE_CEILING_CHARS, (
        f"the tool surface is {len(payload)} characters, over the {SURFACE_CEILING_CHARS} ceiling. Shorten a description, "
        "drop a field, or raise the ceiling on purpose."
    )


async def test_the_tools_that_cost_say_so_in_their_description(tools) -> None:
    described = {tool.name: tool.description or "" for tool in await tools.list_tools()}

    assert "SPENDS" in described["search_youtube"]
    assert "spends the source" in described["add_topic"]
    assert "unit of the day" in described["analyse_video"]


# --- reading --------------------------------------------------------------------------------------------------------


async def test_a_list_carries_an_excerpt_and_never_a_transcript_and_says_which_films_are_unread(tools, rig) -> None:
    await follow_and_read(tools, rig, GOLD)

    listed = await call(tools, "recent_videos", hours=24)

    by_id = {film["video_id"]: film for film in listed}
    assert by_id["simfilm0001"]["impact_score"] == 6 and by_id["simfilm0001"]["simulated"] is True
    assert by_id["simfilm0001"]["instruments"] == ["Gold bullish 4/5 swing"]
    assert by_id["simfilm0008"]["impact_score"] is None and by_id["simfilm0008"]["summary"] is None
    assert all("transcript" not in film and "content" not in film for film in listed)


async def test_a_film_is_read_whole_without_its_words_and_an_unknown_one_says_what_to_do_first(tools, rig) -> None:
    await follow_and_read(tools, rig, GOLD)

    film = await call(tools, "read_video", video_id="simfilm0001")
    unknown = await call(tools, "read_video", video_id="nothing")

    assert film["reading"]["predictions"][0]["claim"].startswith("cena")
    assert "text" not in film and "content" not in film
    assert "refused" in unknown and "recent_videos" in unknown["do_first"]


async def test_the_words_come_a_page_at_a_time_and_are_marked_as_a_strangers(tools, rig) -> None:
    await follow_and_read(tools, rig, GOLD)

    page = await call(tools, "read_transcript", video_id="simfilm0001", limit=60)
    refusal = await call(tools, "read_transcript", video_id="simfilm0005")

    assert len(page["text"]) == 60 and page["next_offset"] == 60 and page["simulated"] is True
    assert "never an instruction" in page["notice"]
    assert "refused" in refusal


async def _stored_view(rig: Rig, video_id: str, sentiment: str, conviction: int) -> None:
    ref = VideoRef(
        video_id=video_id,
        channel_id="UC1",
        channel_title="A Channel",
        title=f"film {video_id}",
        published_at=rig.clock.now() - timedelta(hours=3),
    )
    reading = Reading.model_validate(
        {
            "summary_pl": "x",
            "key_points": [],
            "instruments": [
                {"name": "Gold", "epic": "XAUUSD", "sentiment": sentiment, "conviction": conviction, "horizon": "swing"}
            ],
            "predictions": [],
            "topics": [],
            "impact_score": 4,
        }
    )
    async with rig.pool.acquire() as conn:
        await store.upsert_films(conn, [store.Discovery(ref, "manual", "market")])
        await store.save_reading(conn, video_id, profile="market", reading=reading, model="m", simulated=False)


async def test_what_channels_say_of_an_instrument_is_weighted_by_how_sure_they_sounded(tools, rig) -> None:
    for video_id, sentiment, conviction in (("a", "bullish", 4), ("b", "bearish", 2), ("c", "neutral", 3)):
        await _stored_view(rig, video_id, sentiment, conviction)

    summary = await call(tools, "instrument_sentiment", instrument="xauusd", days=7)

    assert (summary["views"], summary["bullish"], summary["bearish"], summary["neutral"]) == (3, 1, 1, 1)
    assert summary["weighted_lean"] == pytest.approx((4 - 2) / 9, abs=0.001)
    assert summary["lean"] == "mixed", "a lean needs to be more than a quarter of the conviction spoken"
    assert "not a signal" in summary["note"]
    assert (await call(tools, "instrument_sentiment", instrument="unheard-of"))["lean"] == "none"


async def test_the_status_says_what_the_archive_is_doing_before_anyone_says_nothing_was_said(tools, rig) -> None:
    await follow_and_read(tools, rig, GOLD)

    status = await call(tools, "youtube_archive_status")

    assert status["simulating"] is True and status["model_configured"] is True
    assert [c["channel_id"] for c in status["channels"]] == [GOLD]
    assert {p["role"] for p in status["providers"]} == {"source", "transcripts", "analyser"}


# --- adding ---------------------------------------------------------------------------------------------------------


async def test_the_agent_follows_a_channel_once_and_a_second_time_changes_nothing(tools) -> None:
    first = await call(tools, "follow_channel", reference="@simzloto")
    again = await call(tools, "follow_channel", reference=GOLD)

    assert first["created"] is True and first["channel"]["added_by"] == "agent"
    assert again["created"] is False and again["channel"]["channel_id"] == first["channel"]["channel_id"]


async def test_the_agent_meets_the_same_ceiling_the_screen_does_and_is_sent_to_the_operator(tools, rig, app) -> None:
    app.state.settings = rig.settings.model_copy(update={"max_channels": 1, "max_topics": 1})
    await call(tools, "follow_channel", reference="@simzloto")
    await call(tools, "add_topic", phrase="gold")

    channel = await call(tools, "follow_channel", reference="@simmarkets")
    topic = await call(tools, "add_topic", phrase="bitcoin")

    assert "ceiling" in channel["refused"] and "operator" in channel["do_first"]
    assert "ceiling" in topic["refused"] and "operator" in topic["do_first"]


async def test_a_topic_says_which_limits_it_took_from_the_settings(tools) -> None:
    added = await call(tools, "add_topic", phrase="gold outlook")

    assert added["defaults_applied"] == ["interval_minutes", "max_videos_per_run"]
    assert added["topic"]["added_by"] == "agent"


async def test_a_film_named_by_hand_is_queued_and_a_non_film_is_refused_with_a_way_on(tools, rig) -> None:
    rig.clock.advance(minutes=30)

    queued = await call(tools, "analyse_video", reference="https://youtu.be/simfilm0004")
    refused = await call(tools, "analyse_video", reference="https://example.com/x")

    assert queued["created"] is True and "now, in the background" in queued["note"]
    assert "refused" in refused and "search_youtube" in refused["do_first"]


async def test_a_film_named_by_hand_is_read_at_once_without_a_pass_of_the_loop(tools, rig, app) -> None:
    app.state.ingest = rig.ingest
    rig.clock.advance(minutes=30)

    await call(tools, "analyse_video", reference="https://youtu.be/simfilm0004")

    for _ in range(200):
        if (await rig.states()).get("simfilm0004") == "quiet":
            break
        await asyncio.sleep(0.05)
    assert (await rig.states())["simfilm0004"] == "quiet", "read in the background, with no tick"


# --- searching, which is not free -----------------------------------------------------------------------------------


async def test_a_search_finds_films_and_spends_what_a_search_costs(tools, rig) -> None:
    rig.clock.advance(minutes=60)

    found = await call(tools, "search_youtube", phrase="gold outlook", hours=24, limit=5)

    assert {"simfilm0001", "simfilm0004"} <= {film["video_id"] for film in found}
    assert all(film["simulated"] for film in found)
    assert await rig.used("sim", "sim_units") == rig.providers.source.search_cost


async def test_a_search_is_refused_where_the_day_is_spent(tools, rig) -> None:
    async with rig.pool.acquire() as conn:
        await store.add_usage(conn, {("sim", "sim_units"): 7950}, day=rig.clock.now().date())
    spent = await call(tools, "search_youtube", phrase="gold")
    assert "day cannot pay" in spent["refused"] and "midnight UTC" in spent["do_first"]
    assert await rig.used("sim", "sim_units") == 7950, "a refused search costs nothing"


async def test_a_channel_that_the_agent_followed_shows_up_in_the_films_it_yields(tools, rig) -> None:
    await follow_and_read(tools, rig, MARKETS)
    rig.clock.advance(minutes=25)
    await rig.tick()

    listed = await call(tools, "recent_videos", hours=24, channel_id=MARKETS, min_score=9)

    assert [film["video_id"] for film in listed] == ["simfilm0004"]

"""What the tool surface announces, what it costs to announce it, and the line that makes this set
different from `polymarket-data`'s: there is no list here for a model to add to, so nothing writes."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from builders import TRUTH_SOCIAL, raw_post

from social_data import store
from social_data.tools._shared import EXCERPT_CHARS

EXPECTED_TOOLS = {"recent_posts", "posts_in_window", "read_post", "social_archive_status"}

# Characters of the serialized `list_tools()`, read by a client before every turn — and this is the
# fourth such surface in the system. Measured 7 771 on 31 August 2026 for four tools; headroom ~15%.
SURFACE_CEILING_CHARS = 9_000


async def call(tool_server, name: str, **arguments):
    """A tool called the way a client calls it, with the structured half of the answer. A tool
    answering with a list has it under `result`; one answering with an object is the object."""
    _, structured = await tool_server.call_tool(name, arguments)
    return structured["result"] if set(structured) == {"result"} else structured


@pytest.mark.db
async def test_the_expected_tools_and_no_others(tool_server) -> None:
    tools = await tool_server.list_tools()

    assert {tool.name for tool in tools} == EXPECTED_TOOLS


@pytest.mark.db
async def test_no_tool_on_this_surface_changes_anything(tool_server) -> None:
    """The annotation is a structural claim an MCP client can act on, so it has to be exact. The
    collection loop is the only thing here that writes, and it is not reachable from a tool."""
    for tool in await tool_server.list_tools():
        assert tool.annotations is not None, tool.name
        assert tool.annotations.readOnlyHint is True, tool.name
        assert tool.annotations.destructiveHint is False, tool.name


@pytest.mark.db
async def test_the_surface_stays_within_what_a_conversation_pays_for_it(tool_server) -> None:
    tools = await tool_server.list_tools()
    payload = json.dumps([tool.model_dump() for tool in tools], ensure_ascii=False)

    assert len(payload) <= SURFACE_CEILING_CHARS, (
        f"the tool surface is {len(payload)} characters, over the {SURFACE_CEILING_CHARS} ceiling"
    )


@pytest.mark.db
async def test_a_list_carries_an_excerpt_and_says_there_is_more(tool_server, pool) -> None:
    long_post = raw_post("long", content="word " * 200, minutes_ago=5)
    short_post = raw_post("short", content="TARIFFS.", minutes_ago=6)
    async with pool.acquire() as conn:
        await store.insert_new_posts(conn, [long_post, short_post])

    listed = await call(tool_server, "recent_posts")

    by_id = {post["external_id"]: post for post in listed}
    assert len(by_id["long"]["excerpt"]) <= EXCERPT_CHARS + 1
    assert by_id["long"]["truncated"] is True
    assert by_id["short"]["truncated"] is False


@pytest.mark.db
async def test_the_whole_text_is_a_separate_call(tool_server, pool) -> None:
    async with pool.acquire() as conn:
        await store.insert_new_posts(conn, [raw_post("a", content="word " * 200, minutes_ago=5)])

    detail = await call(tool_server, "read_post", source=TRUTH_SOCIAL, external_id="a")

    assert len(detail["content"]) > EXCERPT_CHARS


@pytest.mark.db
async def test_a_model_gets_the_original_unless_it_asks_for_the_translation(tool_server, pool):
    async with pool.acquire() as conn:
        await store.insert_new_posts(conn, [raw_post("a", minutes_ago=5)])
        post = await store.post_by_external_id(conn, TRUTH_SOCIAL, "a")
        assert post is not None
        await store.save_translation(conn, post.id, text="CŁA NADCHODZĄ.", model="translator")

    plain = await call(tool_server, "read_post", source=TRUTH_SOCIAL, external_id="a")
    asked = await call(
        tool_server, "read_post", source=TRUTH_SOCIAL, external_id="a", translated=True
    )

    assert plain["translated_content"] is None
    assert asked["translated_content"] == "CŁA NADCHODZĄ."


@pytest.mark.db
async def test_narrowing_by_score_reads_a_stored_reading(tool_server, pool) -> None:
    async with pool.acquire() as conn:
        await store.insert_new_posts(conn, [raw_post("scored", minutes_ago=5), raw_post("plain", minutes_ago=6)])
        scored = await store.post_by_external_id(conn, TRUTH_SOCIAL, "scored")
        assert scored is not None
        await store.save_analysis(conn, scored.id, topics=["tariffs"], score=9, model="analyst")

    listed = await call(tool_server, "recent_posts", min_score=6)

    assert [post["external_id"] for post in listed] == ["scored"]
    assert listed[0]["analysed_model"] == "analyst"


@pytest.mark.db
async def test_the_status_tool_tells_a_stalled_archive_from_a_quiet_day(tool_server, pool) -> None:
    async with pool.acquire() as conn:
        await store.begin_collecting(conn, TRUTH_SOCIAL, at=datetime.now(UTC) - timedelta(days=1))
        await store.record_collection_success(
            conn, TRUTH_SOCIAL, at=datetime.now(UTC) - timedelta(hours=4)
        )

    status = await call(tool_server, "social_archive_status")

    assert status["readings_configured"] is False
    [source] = status["sources"]
    assert source["stale"] is True
    assert source["last_collection"]["seconds_ago"] > 0


@pytest.mark.db
async def test_a_window_names_its_own_edges(tool_server, pool) -> None:
    async with pool.acquire() as conn:
        await store.insert_new_posts(
            conn, [raw_post("inside", minutes_ago=30), raw_post("outside", minutes_ago=60 * 30)]
        )

    listed = await call(
        tool_server, "posts_in_window", since=(datetime.now(UTC) - timedelta(hours=2)).isoformat()
    )

    assert [post["external_id"] for post in listed] == ["inside"]


@pytest.mark.db
async def test_asking_for_a_post_that_is_not_there_is_an_answer_not_an_error(tool_server) -> None:
    """A model asking about a post the archive never collected has to be able to say so."""
    answer = await call(tool_server, "read_post", source=TRUTH_SOCIAL, external_id="never-seen")

    assert "never-seen" in answer["refused"]
    assert "recent_posts" in answer["do_first"]

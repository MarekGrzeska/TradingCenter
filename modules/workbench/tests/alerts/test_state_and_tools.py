"""How the package says it is doing, and the two tools through which a conversation reads what became of a rule."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from tc_runtime.liveness import Heartbeats, LoopHeartbeat

from alerts import store
from workbench.local_tools import ConversationLocalTools, TeamsLocalTools

from .builders import condition, event, rule

pytestmark = pytest.mark.db

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def beating(app) -> LoopHeartbeat:
    beat = LoopHeartbeat("clock", expected_seconds=5)
    app.state.heartbeats = Heartbeats(beat)
    return beat


async def saved(pool, candidate=None) -> int:
    async with pool.acquire() as conn:
        row = await store.insert_rule(conn, candidate or rule(), created_by="operator", now=NOW)
    return row["id"]


async def test_the_state_counts_rules_and_says_what_the_package_cannot_do(api, pool, db, app) -> None:
    await saved(pool)
    await saved(pool, rule(condition(), name="off", enabled=False))
    app.state.gateway = None
    app.state.drafter = None
    app.state.tools = None

    shown = (await api.get("/state")).json()

    assert (shown["rules_enabled"], shown["rules_disabled"]) == (1, 1)
    assert (shown["delivering"], shown["drafting"], shown["reading_values"]) == (False, False, False)


async def test_a_clock_that_has_never_ticked_says_so_and_how_long_it_has_been(api, beating, db) -> None:
    clock = (await api.get("/state")).json()["clock"]
    assert clock["ran"] is False and clock["expected_seconds"] == 5

    beating.beat()
    assert (await api.get("/state")).json()["clock"]["ran"] is True


async def test_a_recipient_who_is_gone_and_a_schema_that_moved_both_count_as_rules_with_problems(api, pool, door, db) -> None:
    await saved(pool)
    door.names = []

    assert (await api.get("/state")).json()["rules_with_defects"] == 1


async def test_a_rule_is_one_defect_however_many_things_are_wrong_and_many_rules_naming_one_gone_recipient_are_many(
    api, pool, door, db
) -> None:
    for _ in range(3):
        await saved(pool, rule(destination="gone"))
    await saved(pool)
    await db.execute("UPDATE rules SET defect = 'the schema moved' WHERE id = (SELECT min(id) FROM rules)")
    door.names = ["phone"]

    assert (await api.get("/state")).json()["rules_with_defects"] == 3


async def test_a_rule_that_became_ambiguous_because_its_recipient_got_a_second_bot_is_counted_once(api, pool, door) -> None:
    await saved(pool)
    door.bots = {"phone": ["postsbot", "filmsbot"]}

    assert (await api.get("/state")).json()["rules_with_defects"] == 1


async def test_fires_waiting_to_be_retried_are_counted(api, pool, db) -> None:
    rule_id = await saved(pool)
    async with pool.acquire() as conn:
        await store.record_fire(conn, rule_id, edge_at=NOW, text="x", value=1.0, now=NOW)

    assert (await api.get("/state")).json()["waiting_fires"] == 1


@pytest.fixture
def server(app, pool):
    app.state.pool = pool
    app.state.gateway = None
    return app.state.mcp_server


async def test_both_registries_see_the_same_two_tools_and_neither_writes(server) -> None:
    conversation = await ConversationLocalTools("alerts", server).list_tools()
    teams = await TeamsLocalTools("alerts", server).list_tools()

    assert {tool.name for tool in conversation} == {tool.name for tool in teams} == {"alert_rules", "alert_fires"}
    assert all(tool.read_only is True for tool in conversation)


async def test_the_rules_are_read_with_what_each_watches(server, pool, db, door, app) -> None:
    app.state.gateway = door
    await saved(pool, rule(condition(), name="EURUSD over 1.10"))

    answer = await ConversationLocalTools("alerts", server).call("alert_rules", {})

    row = json.loads(answer.text)["rules"][0]
    assert row["name"] == "EURUSD over 1.10"
    assert row["watches"] == "get_last_price(symbol=EURUSD).close gt 1.10, looked at every 60 s"
    assert row["problems"] == []


async def test_the_history_says_why_a_rule_was_quiet(server, pool, db) -> None:
    rule_id = await saved(pool)
    async with pool.acquire() as conn:
        await store.record_check(conn, rule_id, outcome="unavailable", reason="the tool could not be asked", now=NOW)
        await store.record_fire(conn, rule_id, edge_at=NOW, text="EURUSD is over 1.10", value=1.1, now=NOW)

    answer = json.loads((await ConversationLocalTools("alerts", server).call("alert_fires", {"rule_id": rule_id})).text)

    assert [check["what"] for check in answer["checks"]] == ["unavailable"]
    assert [(fire["state"], fire["text"]) for fire in answer["fires"]] == [("pending", "EURUSD is over 1.10")]


async def test_an_event_rule_is_described_by_its_filter(server, pool, db) -> None:
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO event_types (name, description, schema) VALUES ('youtube.film.read', 'd', '{}')")
    await saved(pool, rule(event()))

    row = json.loads((await ConversationLocalTools("alerts", server).call("alert_rules", {})).text)["rules"][0]

    assert row["watches"] == "every youtube.film.read"


async def test_a_clock_that_stopped_says_how_long_ago_and_is_told_apart_from_a_rule_that_never_fired(api, beating) -> None:
    from datetime import timedelta

    beating.beat(datetime.now(UTC) - timedelta(seconds=60))

    clock = (await api.get("/state")).json()["clock"]

    assert clock["ran"] is True
    assert clock["age_seconds"] >= 60 > 3 * clock["expected_seconds"]

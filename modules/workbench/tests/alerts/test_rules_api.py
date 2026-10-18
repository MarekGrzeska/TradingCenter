"""The rules as the terminal writes and reads them. The reasons a rule is refused are `test_validation`'s; here is that they
reach the wire, that a stored rule comes back as it went in, and that the routes only a package may call refuse anyone
else."""

from __future__ import annotations

import pytest

from .builders import FILM_SCHEMA, condition, event, rule

pytestmark = pytest.mark.db

TOOLS_TEXT = {"description": "a film", "schema": FILM_SCHEMA}


def body(candidate) -> dict:
    return candidate.model_dump(mode="json")


async def test_a_rule_comes_back_as_it_was_written_with_the_defaults_of_its_kind(api) -> None:
    created = await api.post("/rules", json=body(rule(condition())))

    assert created.status_code == 201
    saved = created.json()
    assert saved["cooldown_seconds"] == 900
    assert saved["template"] == "{rule}: {value}"
    assert saved["source"]["threshold"] == "1.10"
    assert (await api.get("/rules")).json() == [saved]


async def test_an_event_rule_has_no_cooldown_and_says_the_text_as_given(api, db) -> None:
    await db.execute("INSERT INTO event_types (name, description, schema) VALUES ('youtube.film.read', 'd', '{}')")

    saved = (await api.post("/rules", json=body(rule(event())))).json()

    assert (saved["cooldown_seconds"], saved["template"]) == (0, "{text}")


async def test_a_refused_rule_names_every_field_and_saves_nothing(api) -> None:
    refused = await api.post("/rules", json=body(rule(condition(tool_name="add_channel"), destination="nobody")))

    assert refused.status_code == 422
    assert {defect["field"] for defect in refused.json()["detail"]["defects"]} == {"source.tool_name", "destination"}
    assert (await api.get("/rules")).json() == []


async def test_a_door_that_does_not_answer_saves_nothing_rather_than_trusting_the_name(api, door) -> None:
    door.down = True

    refused = await api.post("/rules", json=body(rule()))

    assert refused.status_code == 503
    assert (await api.get("/rules")).json() == []


async def test_a_recipient_who_disappears_is_a_defect_on_the_list_and_not_a_deleted_rule(api, door) -> None:
    await api.post("/rules", json=body(rule()))

    door.names = []
    listed = (await api.get("/rules")).json()

    assert [defect["field"] for defect in listed[0]["defects"]] == ["destination"]


async def test_replacing_a_rule_forgets_what_it_had_learned(api, db) -> None:
    saved = (await api.post("/rules", json=body(rule()))).json()
    await db.execute("UPDATE rules SET last_result = true, last_known_result = true WHERE id = $1", saved["id"])

    again = (await api.put(f"/rules/{saved['id']}", json=body(rule(condition(threshold="1.20"))))).json()

    assert again["last_result"] is None
    assert again["source"]["threshold"] == "1.20"


async def test_a_rule_is_switched_off_with_a_reason_and_on_again(api) -> None:
    saved = (await api.post("/rules", json=body(rule()))).json()

    off = (await api.patch(f"/rules/{saved['id']}", json={"enabled": False})).json()
    on = (await api.patch(f"/rules/{saved['id']}", json={"enabled": True})).json()

    assert (off["enabled"], off["disabled_reason"]) == (False, "switched off by the operator")
    assert (on["enabled"], on["disabled_reason"]) == (True, None)


@pytest.mark.parametrize("verb", ["patch", "put", "delete"])
async def test_a_rule_that_is_not_there_is_not_found(api, verb) -> None:
    call = {
        "patch": lambda: api.patch("/rules/9", json={"enabled": True}),
        "put": lambda: api.put("/rules/9", json=body(rule())),
        "delete": lambda: api.delete("/rules/9"),
    }[verb]

    assert (await call()).status_code == 404


async def test_a_rule_is_deleted(api) -> None:
    saved = (await api.post("/rules", json=body(rule()))).json()

    assert (await api.delete(f"/rules/{saved['id']}")).status_code == 204
    assert (await api.get("/rules")).json() == []


async def test_the_catalogue_offers_only_what_reads_and_says_which_fields_are_numbers(api, inside) -> None:
    assert (await inside.put("/event-types/youtube.film.read", json=TOOLS_TEXT)).status_code == 204

    offered = (await api.get("/catalog")).json()

    assert [tool["name"] for tool in offered["tools"]] == ["get_last_price"]
    assert offered["tools"][0]["number_fields"] == ["close", "age_seconds"]
    assert [one["name"] for one in offered["event_types"]] == ["youtube.film.read"]
    assert offered["gateway"] is True
    assert [one["name"] for one in offered["destinations"]] == ["phone"]


async def test_an_announcement_from_outside_is_refused_and_from_the_process_is_kept(api, inside) -> None:
    from_outside = await api.put("/event-types/youtube.film.read", json=TOOLS_TEXT)
    from_inside = await inside.put("/event-types/youtube.film.read", json=TOOLS_TEXT)

    assert from_outside.status_code == 403
    assert from_inside.status_code == 204
    assert [one["name"] for one in (await api.get("/catalog")).json()["event_types"]] == ["youtube.film.read"]


async def test_a_new_schema_that_loses_an_attribute_flags_the_rule_that_used_it_and_keeps_it(api, inside) -> None:
    await inside.put("/event-types/youtube.film.read", json=TOOLS_TEXT)
    used = [{"attribute": "channel", "op": "eq", "value": "Some channel"}]
    saved = (await api.post("/rules", json={**body(rule(event())), "source": {"kind": "event", "event_type": "youtube.film.read", "filter": used}})).json()

    thinner = {"description": "a film", "schema": {"type": "object", "properties": {"text": {"type": "string"}}}}
    await inside.put("/event-types/youtube.film.read", json=thinner)
    listed = (await api.get("/rules")).json()

    assert [one["id"] for one in listed] == [saved["id"]]
    assert "source.filter.0.attribute" in listed[0]["defects"][0]["message"]
    await inside.put("/event-types/youtube.film.read", json=TOOLS_TEXT)
    assert (await api.get("/rules")).json()[0]["defects"] == []


async def test_the_history_of_a_rule_says_what_it_did_and_why_it_could_not(api, pool) -> None:
    from datetime import UTC, datetime

    from alerts import store

    saved = (await api.post("/rules", json=body(rule()))).json()
    now = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
    async with pool.acquire() as conn:
        await store.record_check(conn, saved["id"], outcome="unavailable", reason="market-data could not answer", now=now)
        await store.record_fire(conn, saved["id"], edge_at=now, text="EURUSD is over 1.10", value=1.1, now=now)

    shown = (await api.get(f"/rules/{saved['id']}/history")).json()

    assert [(one["state"], one["text"]) for one in shown["fires"]] == [("pending", "EURUSD is over 1.10")]
    assert [(one["outcome"], one["reason"]) for one in shown["checks"]] == [("unavailable", "market-data could not answer")]
    assert (await api.get("/rules/999/history")).status_code == 404


async def test_the_catalogue_offers_the_pairs_the_archive_follows_and_the_values_an_attribute_has_had(api, inside, tools) -> None:
    schema = {"type": "object", "properties": {"channel": {"type": "string", "x-seen-values": True}, "title": {"type": "string"}}}
    await inside.put("/event-types/youtube.film.read", json={"description": "a film", "schema": schema})
    for key, channel in (("a", "Gold Talk"), ("b", "Gold Talk"), ("c", "Macro")):
        await inside.post("/events", json={"type": "youtube.film.read", "source_key": key, "attributes": {"channel": channel, "title": key}, "text": "x"})

    from .builders import tool

    tools.add(tool("list_tracked_symbols", input_schema={"type": "object", "properties": {}}, output_schema={}))

    offered = (await api.get("/catalog")).json()

    assert offered["event_types"][0]["seen"] == {"channel": ["Gold Talk", "Macro"]}
    assert offered["symbols"] == ["EURUSD", "XAUUSD"]

"""Revisions as the database keeps them: never changed, numbered in order, not repeated for the same content, and never
deleted (`strategies-documents`)."""

from __future__ import annotations

import json

import pytest

from strategies import store
from strategies.document import servable, validate

from .builders import TRACKED, catalogue, document

pytestmark = pytest.mark.db


def checked(**changes):
    found, problems = validate(document(**changes), catalogue(), servable(TRACKED))
    assert found is not None, problems
    return found


async def test_an_edit_is_the_next_revision_and_the_previous_one_stays_as_it_was(pool) -> None:
    first = await store.create(pool, checked(), "operator")
    async with pool.acquire() as conn:
        before = await conn.fetchrow("SELECT document::text, content_hash FROM strategy_revisions WHERE n = 1")

    second = await store.save_revision(pool, first.strategy_id, checked(name="renamed"), "operator")

    async with pool.acquire() as conn:
        after = await conn.fetchrow("SELECT document::text, content_hash FROM strategy_revisions WHERE n = 1")
        summary = await store.get_strategy(conn, first.strategy_id)
    assert (second.revision, second.created) == (2, True)
    assert before == after
    assert (summary.name, summary.latest_revision) == ("renamed", 2)


async def test_saving_the_same_content_again_creates_nothing_and_answers_the_latest(pool) -> None:
    first = await store.create(pool, checked(), "operator")

    again = await store.save_revision(pool, first.strategy_id, checked(), "agent")

    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT count(*) FROM strategy_revisions")
    assert (again.revision, again.created, count) == (1, False, 1)


async def test_an_archived_strategy_leaves_the_list_and_keeps_its_runs(pool) -> None:
    saved = await store.create(pool, checked(), "operator")
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO runs (strategy_id, revision, request, status) VALUES ($1, 1, $2::jsonb, 'done')",
            saved.strategy_id, json.dumps({}),
        )
        archived = await store.set_archived(conn, saved.strategy_id, True)
        listed = await store.list_strategies(conn)
        only_archived = await store.list_strategies(conn, archived=True)
        runs = await conn.fetchval("SELECT count(*) FROM runs WHERE strategy_id = $1", saved.strategy_id)

    assert archived.archived_at is not None and archived.trials == 1
    assert listed == [] and [s.id for s in only_archived] == [saved.strategy_id]
    assert runs == 1


async def test_a_revision_is_read_by_number_or_as_the_latest(pool) -> None:
    saved = await store.create(pool, checked(), "operator")
    await store.save_revision(pool, saved.strategy_id, checked(name="second"), "operator")

    async with pool.acquire() as conn:
        latest = await store.get_revision(conn, saved.strategy_id)
        first = await store.get_revision(conn, saved.strategy_id, 1)
        with pytest.raises(store.NotFound):
            await store.get_revision(conn, saved.strategy_id, 9)

    assert (latest.n, latest.document["name"]) == (2, "second")
    assert first.document["name"] == document()["name"]


async def test_a_save_based_on_a_revision_no_longer_the_latest_is_a_conflict_and_saves_nothing(pool) -> None:
    first = await store.create(pool, checked(), "operator")
    await store.save_revision(pool, first.strategy_id, checked(name="agent's"), "agent", based_on=1)

    with pytest.raises(store.Conflict) as refused:
        await store.save_revision(pool, first.strategy_id, checked(name="operator's"), "operator", based_on=1)
    unchanged = await store.save_revision(pool, first.strategy_id, checked(name="agent's"), "operator", based_on=1)

    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT count(*) FROM strategy_revisions")
    assert refused.value.latest == 2 and count == 2
    assert (unchanged.revision, unchanged.created) == (2, False)

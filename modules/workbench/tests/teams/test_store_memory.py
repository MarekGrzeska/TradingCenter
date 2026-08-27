"""What a team remembers, against a real PostgreSQL. What is under test is the owner filter riding inside
every statement, the order the read comes back in, and what survives retiring a team."""

from __future__ import annotations

import asyncpg
import pytest

from teams import store
from teams.contract import AgentDefinition, TeamDefinition, TeamEdge

pytestmark = pytest.mark.db

OWNER = "operator-1"
STRANGER = "operator-2"


def _definition() -> TeamDefinition:
    return TeamDefinition(
        agents=[
            AgentDefinition(key="scout", role="scout", prompt="read the chart", model_id="luna"),
            AgentDefinition(key="judge", role="judge", prompt="weigh it", model_id="luna"),
        ],
        edges=[TeamEdge(from_="scout", to="judge")],
    )


async def _team(db: asyncpg.Connection, *, owner: str = OWNER, name: str = "morning desk"):
    return await store.create_team(
        db, owner_principal=owner, name=name, description="", definition=_definition()
    )


async def _run(db: asyncpg.Connection, revision_id: int, *, owner: str = OWNER) -> int:
    run, _steps = await store.create_run(
        db, team_revision_id=revision_id, owner_principal=owner, agent_keys=["scout", "judge"]
    )
    return run["id"]


async def _remember(
    db: asyncpg.Connection,
    team_id: int,
    content: str,
    *,
    owner: str = OWNER,
    agent_key: str = "scout",
    run_id: int | None = None,
) -> asyncpg.Record | None:
    return await store.add_memory(
        db,
        team_id=team_id,
        owner_principal=owner,
        author_agent_key=agent_key,
        run_id=run_id,
        content=content,
    )


async def test_an_entry_comes_back_with_what_was_written(db: asyncpg.Connection) -> None:
    team, revision = await _team(db)
    run_id = await _run(db, revision["id"])

    entry = await _remember(db, team["id"], "gap opens usually close by noon", run_id=run_id)

    assert entry is not None
    assert entry["content"] == "gap opens usually close by noon"
    assert entry["author_agent_key"] == "scout"
    assert entry["run_id"] == run_id


async def test_the_read_hands_back_the_newest_first_and_the_total(db: asyncpg.Connection) -> None:
    team, _ = await _team(db)
    for content in ("first", "second", "third"):
        await _remember(db, team["id"], content)

    rows, total = await store.list_memories(
        db, team_id=team["id"], owner_principal=OWNER, limit=10
    )

    assert [row["content"] for row in rows] == ["third", "second", "first"]
    assert total == 3


async def test_the_read_says_there_is_more_than_it_handed_over(db: asyncpg.Connection) -> None:
    # specs/teams-memory, "Odczyt oddaje najnowsze wpisy, a nie całą pamięć": a cut the
    # reader cannot see is a memory the model believes is complete.
    team, _ = await _team(db)
    for index in range(5):
        await _remember(db, team["id"], f"entry {index}")

    rows, total = await store.list_memories(
        db, team_id=team["id"], owner_principal=OWNER, limit=2
    )

    assert [row["content"] for row in rows] == ["entry 4", "entry 3"]
    assert total == 5


async def test_a_team_that_has_not_remembered_anything_reads_empty(
    db: asyncpg.Connection,
) -> None:
    team, _ = await _team(db)

    rows, total = await store.list_memories(
        db, team_id=team["id"], owner_principal=OWNER, limit=10
    )

    assert rows == []
    assert total == 0


async def test_a_stranger_cannot_write_into_somebody_elses_team(db: asyncpg.Connection) -> None:
    team, _ = await _team(db)

    entry = await _remember(db, team["id"], "not mine to write", owner=STRANGER)

    assert entry is None
    _rows, total = await store.list_memories(
        db, team_id=team["id"], owner_principal=OWNER, limit=10
    )
    assert total == 0


async def test_a_stranger_reads_nothing_of_somebody_elses_memory(db: asyncpg.Connection) -> None:
    team, _ = await _team(db)
    await _remember(db, team["id"], "mine")

    rows, total = await store.list_memories(
        db, team_id=team["id"], owner_principal=STRANGER, limit=10
    )

    assert rows == []
    assert total == 0


async def test_memory_does_not_reach_across_teams(db: asyncpg.Connection) -> None:
    first, _ = await _team(db, name="morning desk")
    second, _ = await _team(db, name="evening desk")
    await _remember(db, first["id"], "morning note")

    rows, total = await store.list_memories(
        db, team_id=second["id"], owner_principal=OWNER, limit=10
    )

    assert rows == []
    assert total == 0


async def test_the_operator_deletes_one_entry_and_the_rest_stay(db: asyncpg.Connection) -> None:
    team, _ = await _team(db)
    await _remember(db, team["id"], "keep me")
    doomed = await _remember(db, team["id"], "delete me")
    assert doomed is not None

    deleted = await store.delete_memory(
        db, entry_id=doomed["id"], team_id=team["id"], owner_principal=OWNER
    )

    assert deleted is True
    rows, total = await store.list_memories(
        db, team_id=team["id"], owner_principal=OWNER, limit=10
    )
    assert [row["content"] for row in rows] == ["keep me"]
    assert total == 1


async def test_a_stranger_cannot_delete_an_entry(db: asyncpg.Connection) -> None:
    team, _ = await _team(db)
    entry = await _remember(db, team["id"], "mine")
    assert entry is not None

    deleted = await store.delete_memory(
        db, entry_id=entry["id"], team_id=team["id"], owner_principal=STRANGER
    )

    assert deleted is False
    _rows, total = await store.list_memories(
        db, team_id=team["id"], owner_principal=OWNER, limit=10
    )
    assert total == 1


async def test_deleting_an_entry_that_is_not_there_is_false_not_an_error(
    db: asyncpg.Connection,
) -> None:
    team, _ = await _team(db)

    assert (
        await store.delete_memory(
            db, entry_id=9_999_999, team_id=team["id"], owner_principal=OWNER
        )
        is False
    )


async def test_the_run_write_count_is_per_run(db: asyncpg.Connection) -> None:
    team, revision = await _team(db)
    first_run = await _run(db, revision["id"])
    second_run = await _run(db, revision["id"])
    await _remember(db, team["id"], "one", run_id=first_run)
    await _remember(db, team["id"], "two", run_id=first_run)
    await _remember(db, team["id"], "three", run_id=second_run)

    assert await store.count_memories_for_run(db, run_id=first_run) == 2
    assert await store.count_memories_for_run(db, run_id=second_run) == 1


async def test_retiring_a_team_leaves_its_memory_readable(db: asyncpg.Connection) -> None:
    # specs/teams-memory, "Wycofanie zespołu z katalogu nie zabiera jego pamięci".
    team, _ = await _team(db)
    await _remember(db, team["id"], "learned the hard way")

    await store.archive_team(db, team_id=team["id"], owner_principal=OWNER)

    rows, total = await store.list_memories(
        db, team_id=team["id"], owner_principal=OWNER, limit=10
    )
    assert [row["content"] for row in rows] == ["learned the hard way"]
    assert total == 1


async def test_a_run_in_flight_can_still_write_to_a_retired_team(
    db: asyncpg.Connection,
) -> None:
    # A team retired mid-run finishes the run it already started, and what that run
    # worked out is not thrown away on the way out — see `add_memory`'s docstring.
    team, revision = await _team(db)
    run_id = await _run(db, revision["id"])
    await store.archive_team(db, team_id=team["id"], owner_principal=OWNER)

    entry = await _remember(db, team["id"], "written on the way out", run_id=run_id)

    assert entry is not None


async def test_an_entry_too_long_is_refused_by_the_database(db: asyncpg.Connection) -> None:
    # The ceiling is stated in the module *and* here, because this is the only one of the
    # three whose breach would land on disk.
    from teams.contract import MEMORY_ENTRY_MAX_CHARS

    team, _ = await _team(db)

    with pytest.raises(asyncpg.CheckViolationError):
        await _remember(db, team["id"], "x" * (MEMORY_ENTRY_MAX_CHARS + 1))


async def test_an_empty_entry_is_refused_by_the_database(db: asyncpg.Connection) -> None:
    team, _ = await _team(db)

    with pytest.raises(asyncpg.CheckViolationError):
        await _remember(db, team["id"], "")
